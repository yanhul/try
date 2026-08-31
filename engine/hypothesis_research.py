"""Evaluate pre-registered signal filters without changing execution semantics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .features import extract_features
from .execution import execute_trades
from .ledger import build_ledger
from .metrics import Trade, calculate_metrics
from .risk_exit import FixedRiskRewardExit
from .strategy import ReferenceStrategy
from .hypotheses import HYPOTHESES


def _sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _trade_metrics(bars, ledger, stop, rr, cost):
    executed, skipped = execute_trades(bars, ledger, FixedRiskRewardExit(stop, rr))
    trades = [Trade(t.ledger_trade.entry_price, t.exit.price,
                     t.ledger_trade.direction.value,
                     t.ledger_trade.entry_bar, t.exit.bar_index, t.exit.reason)
              for t in executed]
    return calculate_metrics(trades, cost), skipped


def evaluate_split(bars, start, end, hypothesis, stop=0.01, rr=2.0, cost=0.0):
    history = bars[:end]
    events = ReferenceStrategy().process(history)
    ledger = [t for t in build_ledger(events) if start <= t.entry_bar < end]
    features = extract_features(history)
    predicate = HYPOTHESES[hypothesis]
    filtered = []
    for t in ledger:
        ctx = {"sweep": features[t.sweep_bar], "mss": features[t.mss_bar],
               "fvg": features[t.fvg_bar], "entry": features[t.entry_bar]}
        if predicate(ctx, t.direction.value):
            filtered.append(t)
    metrics, skipped = _trade_metrics(history, filtered, stop, rr, cost)
    return {"candidate_trades": len(ledger), "accepted_signals": len(filtered),
            "skipped_overlap_trades": skipped, "metrics": metrics}


def run_hypothesis_research(csv_path, output_path, *, stop=0.01, rr=2.0,
                            round_trip_cost=0.0):
    bars = load_bars(csv_path)
    splits = chronological_split(len(bars))
    validate_splits(splits, len(bars))
    result = {
        "schema_version": 1,
        "protocol": {
            "hypothesis_selection": "pre_registered_fixed_rules",
            "parameter_selection": "none",
            "execution": "shared_reference_execution",
            "oos": "descriptive_only_after_is_validation_gate",
        },
        "dataset": {"bars": len(bars), "sha256": _sha256(csv_path)},
        "execution": {"stop_fraction": stop, "reward_multiple": rr,
                       "round_trip_cost": round_trip_cost},
        "hypotheses": {},
    }
    # Research discipline: do not rank hypotheses on OOS. Report IS/VAL first;
    # OOS is only reported for hypotheses whose validation passes.
    for name in HYPOTHESES:
        is_result = evaluate_split(bars, splits[0].start, splits[0].end,
                                   name, stop, rr, round_trip_cost)
        val_result = evaluate_split(bars, splits[1].start, splits[1].end,
                                    name, stop, rr, round_trip_cost)
        vm = val_result["metrics"]
        passed = (vm["profit_factor"] is not None and
                  vm["profit_factor"] >= 1.0 and vm["total_return"] >= 0.0)
        oos = None
        if passed:
            oos = evaluate_split(bars, splits[2].start, splits[2].end,
                                  name, stop, rr, round_trip_cost)
        result["hypotheses"][name] = {"IS": is_result, "VALIDATION": val_result,
                                      "validation_passed": passed, "OOS": oos}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
