"""AIOS workload adapter for the deterministic research workload."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from engine.backtest import run_backtest


def execute(*, problem: str, workdir: str | Path = ".") -> dict[str, Any]:
    """Execute one bounded research workload and return evidence-bound result."""
    if not isinstance(problem, str) or not problem.strip():
        raise ValueError("problem must be non-empty")
    root = Path(workdir)
    data = root / "data" / "BTCUSDT_1h.csv"
    if not data.exists():
        return {"status": "BLOCKED", "reason": "required research dataset missing"}
    result = run_backtest(data)
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "status": "PASS",
        "problem": problem,
        "artifact": "research/backtest.json",
        "evidence": {
            "dataset": str(data),
            "dataset_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
            "result_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "bars": result["data"]["bars"],
            "events": len(result["events"]),
        },
        "result": result,
    }


if __name__ == "__main__":
    print(json.dumps(execute(problem="AIOS conformance research workload"), indent=2))
