"""Leakage-resistant IS -> Validation -> locked OOS research pipeline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .split_research import run_split


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
) -> dict:
    """Select on IS, gate on validation, then evaluate the selected config once on OOS.

    OOS is never used to rank, filter, or select candidates.
    """
    bars = load_bars(csv_path)
    splits = chronological_split(len(bars), is_ratio, validation_ratio)
    validate_splits(splits, len(bars))
    candidates = list(candidates)
    if not candidates:
        raise ValueError("no candidates")

    is_results = []
    for config in candidates:
        stop, rr = _validate_config(config)
        result = run_split(bars, splits[0].start, splits[0].end, stop, rr)
        is_results.append({
            "config": {"stop_fraction": stop, "reward_multiple": rr},
            "result": result,
            "score": _score(result["metrics"], objective),
        })

    # Deterministic ranking: objective first, then lower stop, then RR.
    is_results.sort(
        key=lambda x: (
            x["score"],
            -x["config"]["stop_fraction"],
            x["config"]["reward_multiple"],
        ),
        reverse=True,
    )
    selected = is_results[0]
    stop, rr = _validate_config(selected["config"])

    validation = run_split(
        bars, splits[1].start, splits[1].end, stop, rr
    )
    vm = validation["metrics"]
    validation_pass = (
        (vm.get("profit_factor") is not None)
        and vm["profit_factor"] >= validation_min_profit_factor
        and vm["total_return"] >= validation_min_total_return
    )

    # OOS is deliberately evaluated only after the validation gate and is never
    # consulted by the selection logic.
    oos = None
    if validation_pass:
        oos = run_split(bars, splits[2].start, splits[2].end, stop, rr)

    result = {
        "schema_version": 1,
        "dataset": {
            "bars": len(bars),
            "sha256": _sha256(csv_path),
        },
        "protocol": {
            "selection": "IS_only",
            "validation": "gate_only",
            "oos": "locked_single_evaluation",
            "objective": objective,
            "validation_min_profit_factor": validation_min_profit_factor,
            "validation_min_total_return": validation_min_total_return,
        },
        "splits": {s.name: {"start": s.start, "end": s.end} for s in splits},
        "candidate_count": len(is_results),
        "is_ranking": is_results,
        "selected_config": selected["config"],
        "validation": {
            "result": validation,
            "passed": validation_pass,
        },
        "oos": oos,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
