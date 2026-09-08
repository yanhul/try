"""AIOS workload adapter for the deterministic final research workload."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROVENANCE = {"producer": "yanhul/try", "adapter": "try.research@1"}
DATASET = Path("data/BTCUSDT_1h.csv")
RESULT = Path("research/final_strategy_result.json")
CANDIDATES = Path("research/final_candidates.json")
DIAGNOSTIC = Path("research/final_strategy_error.json")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_failure(root: Path, stage: str, proc: subprocess.CompletedProcess[str]) -> str:
    """Persist bounded deterministic diagnostics without making failure opaque."""
    payload = {
        "schema_version": 1,
        "stage": stage,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "provenance": PROVENANCE,
    }
    path = root / DIAGNOSTIC
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(DIAGNOSTIC)


def execute(*, problem: str, workdir: str | Path = ".") -> dict[str, Any]:
    if not isinstance(problem, str) or not problem.strip():
        raise ValueError("problem must be non-empty")
    root = Path(workdir)
    data = root / DATASET
    result_path = root / RESULT
    candidates = root / CANDIDATES
    if not candidates.exists():
        return {"status": "BLOCKED", "reason": "final candidate set missing", "artifact_refs": (),
                "evidence_refs": (), "verification_refs": (), "provenance": PROVENANCE}

    if not data.exists():
        cmd = [sys.executable, "engine/binance_downloader.py", "--symbol", "BTCUSDT",
               "--interval", "1h", "--start", "2026-01-01T00:00:00Z",
               "--end", "2026-06-01T00:00:00Z", "--out", str(DATASET)]
        proc = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=300, check=False)
        if proc.returncode != 0 or not data.exists():
            diagnostic = _record_failure(root, "locked_dataset_download", proc)
            return {"status": "BLOCKED", "reason": "locked dataset download failed",
                    "evidence_refs": ("dataset-download-failed",),
                    "verification_refs": ("locked_dataset",),
                    "artifact_refs": (diagnostic,), "provenance": PROVENANCE}

    cmd = [sys.executable, "run_research_pipeline.py", "--data", str(DATASET),
           "--candidates", str(CANDIDATES), "--out", str(RESULT), "--objective", "profit_factor",
           "--validation-min-pf", "1.0", "--validation-min-return", "0.0"]
    proc = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=600, check=False)
    if proc.returncode != 0 or not result_path.exists():
        diagnostic = _record_failure(root, "final_is_validation_oos_pipeline", proc)
        return {"status": "BLOCKED", "reason": "final IS-validation-OOS pipeline failed",
                "evidence_refs": ("pipeline-failed",), "verification_refs": ("research_pipeline",),
                "artifact_refs": (diagnostic,), "provenance": PROVENANCE}

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    validation = payload.get("validation") or {}
    oos = payload.get("oos")
    if not validation.get("passed") or oos is None:
        return {"status": "BLOCKED", "reason": "validation gate did not pass or OOS missing",
                "artifact_refs": (str(RESULT),),
                "evidence_refs": (f"dataset-sha256:{_digest(data)}", f"result-sha256:{_digest(result_path)}"),
                "verification_refs": ("IS", "validation_gate", "OOS"), "provenance": PROVENANCE}

    metrics = oos.get("metrics", {})
    return {"status": "PASS", "problem": problem,
            "artifact_refs": (str(RESULT),),
            "evidence_refs": (f"dataset-sha256:{_digest(data)}", f"result-sha256:{_digest(result_path)}"),
            "verification_refs": ("regression_tests", "locked_validation", "OOS", "provenance"),
            "provenance": PROVENANCE,
            "metrics": {k: metrics.get(k) for k in ("total_return", "profit_factor", "max_drawdown", "win_rate", "trades")},
            "selected_config": payload.get("selected_config")}


if __name__ == "__main__":
    print(json.dumps(execute(problem="AIOS final research workload"), indent=2))
