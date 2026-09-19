#!/usr/bin/env python3
"""Strict fast gate for the pre-existing BC1 baseline artifact."""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
artifact = ROOT / "research" / "BTCUSDT_1h_hypotheses_v1.json"
data = json.loads(artifact.read_text(encoding="utf-8"))


def validate_baseline(data):
    """Validate BC1 from the artifact itself; callers can unit-test mutations."""
    if not isinstance(data, dict):
        raise ValueError("BC1 artifact must be an object")
    hypotheses = data.get("hypotheses")
    if not isinstance(hypotheses, dict) or not isinstance(hypotheses.get("baseline"), dict):
        raise ValueError("BC1 baseline hypothesis missing")
    base = hypotheses["baseline"]
    validation = base.get("VALIDATION")
    if not isinstance(validation, dict):
        raise ValueError("BC1 VALIDATION section missing")
    if base.get("validation_passed") is not False:
        raise ValueError("BC1 bootstrap gate requires recorded validation_passed=false")
    if base.get("OOS") is not None:
        raise ValueError("BC1 must not contain OOS evidence before validation promotion")

    metrics = validation.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("BC1 validation metrics missing")

    required = {
        "trade_count", "win_count", "loss_count", "win_rate",
        "total_return", "avg_return", "profit_factor", "max_drawdown",
    }
    missing = sorted(required - metrics.keys())
    if missing:
        raise ValueError(f"BC1 validation metrics missing fields: {','.join(missing)}")

    try:
        trade_count = int(metrics["trade_count"])
        win_count = int(metrics["win_count"])
        loss_count = int(metrics["loss_count"])
        win_rate = float(metrics["win_rate"])
        total_return = float(metrics["total_return"])
        avg_return = float(metrics["avg_return"])
        profit_factor = float(metrics["profit_factor"])
        max_drawdown = float(metrics["max_drawdown"])
    except (TypeError, ValueError):
        raise ValueError("BC1 validation metrics contain non-numeric values")

    if trade_count < 0 or win_count < 0 or loss_count < 0:
        raise ValueError("BC1 validation counts must be non-negative")
    if win_count + loss_count != trade_count:
        raise ValueError("BC1 validation trade_count != win_count + loss_count")

    for name, value in {
        "win_rate": win_rate,
        "total_return": total_return,
        "avg_return": avg_return,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
    }.items():
        if not math.isfinite(value):
            raise ValueError(f"BC1 validation metric {name} is not finite")

    if trade_count == 0:
        if win_rate != 0.0:
            raise ValueError("BC1 zero-trade validation must have win_rate=0")
    elif not math.isclose(
        win_rate, win_count / trade_count, rel_tol=1e-12, abs_tol=1e-12
    ):
        raise ValueError("BC1 validation win_rate is inconsistent with trade counts")

    expected = profit_factor >= 1.0 and total_return >= 0.0
    if base["validation_passed"] != expected:
        raise ValueError("BC1 validation_passed disagrees with authoritative validation predicate")

    return metrics


if __name__ == "__main__":
    try:
        metrics = validate_baseline(data)
    except ValueError as exc:
        raise SystemExit(f"BLOCKED: {exc}")

    print("BC1_VALIDATION_FAIL", metrics)
    print("SPLIT_GATE False")
    print("REJECT_BC")
