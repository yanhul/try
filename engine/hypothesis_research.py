"""Evaluate atomic and bounded composite hypotheses under the same execution model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .features import extract_features
from .specific_features import extract_specific_features
from .context_features import gann_reference, point_figure_columns, PnFConfig, rolling_volatility, vwap
from .execution import execute_trades
from .ledger import build_ledger
from .metrics import Trade, calculate_metrics
from .risk_exit import FixedRiskRewardExit
from .strategy import ReferenceStrategy
from .hypotheses import HYPOTHESES
from .composition import generate_composites


def _sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()


def _trade_metrics(bars, ledger, stop, rr, cost):
    executed, skipped = execute_trades(bars, ledger, FixedRiskRewardExit(stop, rr))
    trades = [Trade(t.ledger_trade.entry_price, t.exit.price,
                     t.ledger_trade.direction.value,
                     t.ledger_trade.entry_bar, t.exit.bar_index, t.exit.reason)
              for t in executed]
    return calculate_metrics(trades, cost), skipped


def evaluate_split(bars, start, end, predicate, stop=0.01, rr=2.0, cost=0.0):
    history = bars[:end]
    events = ReferenceStrategy().process(history)
    ledger = [t for t in build_ledger(events) if start <= t.entry_bar < end]
    features = extract_features(history)
    specific = extract_specific_features(history)
    vol = rolling_volatility(history)
    vw = vwap(history)
    gann = gann_reference(history)
    pnf_direction: list[str | None] = []
    box = max(1e-9, (max(b.high for b in history) - min(b.low for b in history)) / 100.0) if history else 1.0
    for i in range(len(history)):
        cols = point_figure_columns(history[:i + 1], PnFConfig(box_size=box))
        pnf_direction.append(cols[-1]["direction"] if cols else None)
    filtered = []
    for t in ledger:
        def row(index):
            base = dict(features[index])
            base.update(specific[index])
            base["volatility"] = vol[index]
            base["vwap"] = vw[index]
            base["vwap_distance"] = ((history[index].close - vw[index]) / vw[index]) if vw[index] else None
            base["gann_slope"] = gann[index]["slope"]
            base["pnf_direction"] = pnf_direction[index]
            return base
        ctx = {"sweep": row(t.sweep_bar), "mss": row(t.mss_bar),
               "fvg": row(t.fvg_bar), "entry": row(t.entry_bar)}
        if predicate(ctx, t.direction.value):
            filtered.append(t)
    metrics, skipped = _trade_metrics(history, filtered, stop, rr, cost)
    return {"candidate_trades": len(ledger), "accepted_signals": len(filtered),
            "skipped_overlap_trades": skipped, "metrics": metrics}


def run_hypothesis_research(csv_path, output_path, *, stop=0.01, rr=2.0,
                            round_trip_cost=0.0, max_components=3):
    bars = load_bars(csv_path)
    splits = chronological_split(len(bars))
    validate_splits(splits, len(bars))
    composites = generate_composites(max_components=max_components)
    candidates = [(n, p) for n, p in HYPOTHESES.items()]
    candidates += [(c.name, c.predicate) for c in composites]
    result = {
        "schema_version": 2,
        "protocol": {
            "hypothesis_selection": "pre_registered_fixed_rules_and_bounded_composition",
            "parameter_selection": "none",
            "execution": "shared_reference_execution",
            "oos": "descriptive_only_after_is_validation_gate",
            "max_components": max_components,
        },
        "dataset": {"bars": len(bars), "sha256": _sha256(csv_path)},
        "execution": {"stop_fraction": stop, "reward_multiple": rr,
                       "round_trip_cost": round_trip_cost},
        "hypotheses": {},
    }
    for name, predicate in candidates:
        is_result = evaluate_split(bars, splits[0].start, splits[0].end,
                                   predicate, stop, rr, round_trip_cost)
        val_result = evaluate_split(bars, splits[1].start, splits[1].end,
                                    predicate, stop, rr, round_trip_cost)
        vm = val_result["metrics"]
        passed = (vm["profit_factor"] is not None and
                  vm["profit_factor"] >= 1.0 and vm["total_return"] >= 0.0)
        oos = None
        if passed:
            oos = evaluate_split(bars, splits[2].start, splits[2].end,
                                  predicate, stop, rr, round_trip_cost)
        result["hypotheses"][name] = {"IS": is_result, "VALIDATION": val_result,
                                      "validation_passed": passed, "OOS": oos}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
