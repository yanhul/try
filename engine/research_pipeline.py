"""Leakage-resistant IS -> Validation -> locked OOS research pipeline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .split_research import run_split
from .strategy import ReferenceStrategy
from .ledger import build_ledger
from .strategy_spec import canonicalize, provenance, strategy_hash


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _score(metrics: dict, objective: str) -> float:
    value = metrics.get(objective)
    if value is None:
        return float("-inf")
    return float(value)


def _validate_config(config: dict) -> tuple[float, float]:
    stop = float(config["stop_fraction"])
    rr = float(config["reward_multiple"])
    if stop <= 0 or rr <= 0:
        raise ValueError("stop_fraction and reward_multiple must be positive")
    return stop, rr


def _passes_validation_gate(metrics: dict, min_profit_factor: float, min_total_return: float) -> bool:
    """Apply PF/return thresholds without mistaking an all-winning sample for no evidence.

    PF is undefined when gross loss is zero. For a non-empty trade sample with
    at least one win and zero losses, PF is mathematically +infinity for a
    threshold comparison. A zero-trade sample always fails closed.
    """
    trade_count = int(metrics.get("trade_count") or 0)
    if trade_count <= 0:
        return False
    loss_count = int(metrics.get("loss_count") or 0)
    win_count = int(metrics.get("win_count") or 0)
    profit_factor = metrics.get("profit_factor")
    pf_ok = (
        profit_factor is not None and float(profit_factor) >= min_profit_factor
    ) or (
        profit_factor is None and loss_count == 0 and win_count > 0 and min_profit_factor <= float("inf")
    )
    total_return = metrics.get("total_return")
    return pf_ok and total_return is not None and float(total_return) >= min_total_return


def run_is_validation_oos(
    csv_path: str | Path,
    output_path: str | Path,
    candidates: Iterable[dict],
    *,
    is_ratio: float = 0.60,
    validation_ratio: float = 0.20,
    objective: str = "profit_factor",
    validation_min_profit_factor: float = 1.0,
    validation_min_total_return: float = 0.0,
    oos_min_profit_factor: float | None = None,
    oos_min_total_return: float | None = None,
) -> dict:
    """Select on IS, gate on validation, then evaluate selected config once on OOS.

    Candidate strategy definitions are canonicalized and hashed. OOS is never used
    to rank, filter, or select candidates. If OOS thresholds are supplied, they are
    an independent post-selection admission gate, not a search signal.
    """
    bars = load_bars(csv_path)
    splits = chronological_split(len(bars), is_ratio, validation_ratio)
    validate_splits(splits, len(bars))
    # Strategy/event generation is candidate-independent for this engine.
    # Compute it once; run_split slices the causal prefix for each split.
    events = ReferenceStrategy().process(bars)
    ledger = build_ledger(events)
    research_context = {"bars": bars, "events": events, "ledger": ledger, "split_cache": {}}
    for split in splits:
        research_context["split_cache"][(int(split.start), int(split.end))] = {
            "events": [e for e in events if e.bar_index < split.end],
            "ledger": [t for t in ledger if split.start <= t.entry_bar < split.end],
        }
    candidates = [canonicalize(c) | {"stop_fraction": c["stop_fraction"], "reward_multiple": c["reward_multiple"]} for c in candidates]
    if not candidates:
        raise ValueError("no candidates")

    evaluator_digest = _sha256(Path(__file__))
    is_results = []
    for config in candidates:
        stop, rr = _validate_config(config)
        result = run_split(bars, splits[0].start, splits[0].end, stop, rr, config.get("execution", {}).get("round_trip_cost", 0.0), config, research_context=research_context)
        is_results.append({
            "config": config,
            "strategy_hash": strategy_hash(config),
            "result": result,
            "score": _score(result["metrics"], objective),
        })

    is_results.sort(
        key=lambda x: (x["score"], -x["config"]["stop_fraction"], x["config"]["reward_multiple"]),
        reverse=True,
    )
    selected = is_results[0]
    stop, rr = _validate_config(selected["config"])
    selected_spec = selected["config"]

    validation = run_split(
        bars, splits[1].start, splits[1].end, stop, rr,
        selected_spec.get("execution", {}).get("round_trip_cost", 0.0), selected_spec,
        research_context=research_context,
    )
    vm = validation["metrics"]
    validation_pass = _passes_validation_gate(
        vm, validation_min_profit_factor, validation_min_total_return
    )

    oos = None
    oos_pass = False
    if validation_pass:
        oos = run_split(
            bars, splits[2].start, splits[2].end, stop, rr,
            selected_spec.get("execution", {}).get("round_trip_cost", 0.0), selected_spec,
            research_context=research_context,
        )
        om = oos["metrics"]
        min_pf = validation_min_profit_factor if oos_min_profit_factor is None else oos_min_profit_factor
        min_return = validation_min_total_return if oos_min_total_return is None else oos_min_total_return
        oos_pass = _passes_validation_gate(om, min_pf, min_return)

    result = {
        "schema_version": 3,
        "dataset": {"bars": len(bars), "sha256": _sha256(csv_path)},
        "evaluator_digest": evaluator_digest,
        "protocol": {
            "selection": "IS_only",
            "validation": "gate_only",
            "oos": "locked_single_evaluation",
            "objective": objective,
            "validation_min_profit_factor": validation_min_profit_factor,
            "validation_min_total_return": validation_min_total_return,
            "oos_min_profit_factor": oos_min_profit_factor,
            "oos_min_total_return": oos_min_total_return,
            "feature_policy": "features_are_hypotheses; no predictive claim without OOS evidence",
        },
        "splits": {s.name: {"start": s.start, "end": s.end} for s in splits},
        "candidate_count": len(is_results),
        "is_ranking": is_results,
        "selected_config": selected_spec,
        "selected_provenance": provenance(selected_spec),
        "validation": {"result": validation, "passed": validation_pass},
        "oos": oos,
        "oos_passed": oos_pass,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
