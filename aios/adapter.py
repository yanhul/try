"""AIOS workload adapter for the deterministic research workload."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from engine.backtest import run_backtest


def execute(*, problem: str, workdir: str | Path = ".") -> dict[str, Any]:
    if not isinstance(problem, str) or not problem.strip():
        raise ValueError("problem must be non-empty")
    root = Path(workdir)
    data = root / "data" / "BTCUSDT_1h.csv"
    provenance = {"producer": "yanhul/try", "adapter": "try.research@1"}
    if not data.exists():
        return {"status": "BLOCKED", "reason": "required research dataset missing",
                "evidence_refs": (), "verification_refs": (), "artifact_refs": (), "provenance": provenance}
    result = run_backtest(data)
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    dataset_digest = hashlib.sha256(data.read_bytes()).hexdigest()
    result_digest = hashlib.sha256(payload.encode()).hexdigest()
    return {
        "status": "PASS", "problem": problem,
        "artifact_refs": ("research/backtest.json",),
        "evidence_refs": (f"dataset-sha256:{dataset_digest}", f"result-sha256:{result_digest}"),
        "verification_refs": ("regression_tests", "locked_validation", "provenance"),
        "provenance": provenance,
        "evidence": {"dataset_sha256": dataset_digest, "result_sha256": result_digest,
                     "bars": result["data"]["bars"], "events": len(result["events"])},
        "result": result,
    }


if __name__ == "__main__":
    print(json.dumps(execute(problem="AIOS conformance research workload"), indent=2))
