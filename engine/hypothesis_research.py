"""Evaluate atomic and bounded composite hypotheses under the same execution model."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .features import extract_features
from .specific_features import extract_specific_features
from .context_features import (
    gann_reference,
    multi_timeframe_context,
    point_figure_directions,
    PnFConfig,
    rolling_volatility,
    rolling_volume_profile_poc,
    vwap,
)
from .execution import execute_trades
from .ledger import build_ledger
from .metrics import Trade, calculate_metrics
from .risk_exit import FixedRiskRewardExit
from .strategy import ReferenceStrategy
from .hypotheses import HYPOTHESES
from .composition import generate_composites


@dataclass(frozen=True)
class PreparedSplit:
    """Immutable per-split research cache shared by every hypothesis."""

    history: list
    ledger: list
    contexts: list[dict[str, dict]]


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


def prepare_split(bars, start, end, *, pnf_box_fraction=0.01):
    """Build all causal features and event/ledger context exactly once for a split."""
    if pnf_box_fraction <= 0:
        raise ValueError("pnf_box_fraction must be positive")
    history = bars[:end]
    events = ReferenceStrategy().process(history)
    ledger = [t for t in build_ledger(events) if start <= t.entry_bar < end]

    features = extract_features(history)
    specific = extract_specific_features(history)
    vol = rolling_volatility(history)
    vw = vwap(history)
    gann = gann_reference(history)
    mtf = multi_timeframe_context(history)
    vp_poc = rolling_volume_profile_poc(history)

    # P&F box size is fixed from the first observed close, not the full split range.
    # This prevents the previous full-history min/max box-size lookahead.
    first_close = abs(history[0].close) if history else 1.0
    box = max(1e-9, first_close * pnf_box_fraction)
    pnf_direction = point_figure_directions(history, PnFConfig(box_size=box))

    def row(index):
        base = dict(features[index])
        base.update(specific[index])
        base["close"] = history[index].close
        base["volatility"] = vol[index]
        base["vwap"] = vw[index]
        base["vwap_distance"] = ((history[index].close - vw[index]) / vw[index]) if vw[index] else None
        base["volume_profile_poc"] = vp_poc[index]
        base.update(mtf[index])
        base["gann_slope"] = gann[index]["slope"]
        base["pnf_direction"] = pnf_direction[index]
        return base

    contexts = [
        {
            "sweep": row(t.sweep_bar),
            "mss": row(t.mss_bar),
            "fvg": row(t.fvg_bar),
            "entry": row(t.entry_bar),
        }
        for t in ledger
    ]
    return PreparedSplit(history=history, ledger=ledger, contexts=contexts)


def evaluate_prepared_split(prepared, predicate, stop=0.01, rr=2.0, cost=0.0):
    """Evaluate a predicate using only the immutable split cache."""
    filtered = [t for t, ctx in zip(prepared.ledger, prepared.contexts)
                if predicate(ctx, t.direction.value)]
    metrics, skipped = _trade_metrics(prepared.history, filtered, stop, rr, cost)
    return {"candidate_trades": len(prepared.ledger), "accepted_signals": len(filtered),
            "skipped_overlap_trades": skipped, "metrics": metrics}


def evaluate_split(bars, start, end, predicate, stop=0.01, rr=2.0, cost=0.0,
                   *, prepared=None, pnf_box_fraction=0.01):
    """Backward-compatible single-split API; uses the same cache path."""
    prepared = prepared or prepare_split(
        bars, start, end, pnf_box_fraction=pnf_box_fraction
    )
    return evaluate_prepared_split(prepared, predicate, stop, rr, cost)


def run_hypothesis_research(csv_path, output_path, *, stop=0.01, rr=2.0,
                            round_trip_cost=0.0, max_components=3,
                            pnf_box_fraction=0.01):
    bars = load_bars(csv_path)
    splits = chronological_split(len(bars))
    validate_splits(splits, len(bars))
    composites = generate_composites(max_components=max_components)
    candidates = [(n, p) for n, p in HYPOTHESES.items()]
    candidates += [(c.name, c.predicate) for c in composites]

    # Expensive causal feature extraction is performed once per split, then reused
    # by every atomic and composite candidate.
    prepared = [
        prepare_split(bars, split.start, split.end, pnf_box_fraction=pnf_box_fraction)
        for split in splits
    ]

    result = {
        "schema_version": 3,
        "protocol": {
            "hypothesis_selection": "pre_registered_fixed_rules_and_bounded_composition",
            "parameter_selection": "none",
            "execution": "shared_reference_execution",
            "oos": "descriptive_only_after_is_validation_gate",
            "max_components": max_components,
            "max_composites": 120,
            "feature_evaluation": "causal_split_cache_once_per_split",
            "pnf_box_fraction": pnf_box_fraction,
        },
        "dataset": {"bars": len(bars), "sha256": _sha256(csv_path)},
        "execution": {"stop_fraction": stop, "reward_multiple": rr,
                       "round_trip_cost": round_trip_cost},
        "hypotheses": {},
    }
    for name, predicate in candidates:
        is_result = evaluate_prepared_split(prepared[0], predicate, stop, rr, round_trip_cost)
        val_result = evaluate_prepared_split(prepared[1], predicate, stop, rr, round_trip_cost)
        vm = val_result["metrics"]
        passed = (vm["profit_factor"] is not None and
                  vm["profit_factor"] >= 1.0 and vm["total_return"] >= 0.0)
        oos = None
        if passed:
            oos = evaluate_prepared_split(prepared[2], predicate, stop, rr, round_trip_cost)
        result["hypotheses"][name] = {"IS": is_result, "VALIDATION": val_result,
                                      "validation_passed": passed, "OOS": oos}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
