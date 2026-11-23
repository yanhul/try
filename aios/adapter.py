"""AIOS workload adapter for the pinned, leakage-resistant research workload."""
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
LOCKED_BASELINE = Path("research/BTCUSDT_1h_IS_VAL_OOS_v1.json")
DIAGNOSTIC = Path("research/final_strategy_error.json")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_failure(root: Path, stage: str, message: str, *, stdout: str = "", stderr: str = "") -> str:
    payload = {"schema_version": 1, "stage": stage, "reason": message,
               "stdout": stdout[-4000:], "stderr": stderr[-4000:], "provenance": PROVENANCE}
    path = root / DIAGNOSTIC
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(DIAGNOSTIC)


def _load_locked_candidates(root: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Use the explicit candidate file, or reconstruct the committed IS ranking.

    The fallback is not a new hypothesis: it replays the exact candidate configs
    already recorded in the immutable IS/validation/OOS audit artifact.
    """
    candidate_path = root / CANDIDATES
    if candidate_path.is_file():
        value = json.loads(candidate_path.read_text(encoding="utf-8"))
        if not isinstance(value, list) or not value:
            raise ValueError("final_candidates.json must contain a non-empty JSON array")
        return value, str(CANDIDATES)

    baseline_path = root / LOCKED_BASELINE
    if not baseline_path.is_file():
        raise ValueError("neither final_candidates.json nor the locked IS/validation/OOS report exists")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    ranking = baseline.get("is_ranking")
    if not isinstance(ranking, list) or not ranking:
        raise ValueError("locked research report has no IS candidate ranking")
    if baseline.get("candidate_count") != len(ranking):
        raise ValueError("locked research report candidate_count disagrees with IS ranking")
    candidates = [item.get("config") for item in ranking]
    if any(not isinstance(c, dict) or "stop_fraction" not in c or "reward_multiple" not in c for c in candidates):
        raise ValueError("locked IS ranking contains malformed strategy configurations")
    selected = baseline.get("selected_config")
    if selected != candidates[0]:
        raise ValueError("locked selected_config is not the top-ranked IS candidate")
    return candidates, str(LOCKED_BASELINE)


def execute(*, problem: str, workdir: str | Path = ".") -> dict[str, Any]:
    if not isinstance(problem, str) or not problem.strip():
        raise ValueError("problem must be non-empty")
    root = Path(workdir)
    data = root / DATASET
    result_path = root / RESULT
    if not data.is_file():
        return {"status": "BLOCKED", "reason": "pinned BTCUSDT 1h dataset missing; no implicit network download",
                "artifact_refs": (), "evidence_refs": (), "verification_refs": ("locked_dataset",),
                "provenance": PROVENANCE}

    try:
        candidates, candidate_source = _load_locked_candidates(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        diagnostic = _record_failure(root, "candidate_resolution", str(exc))
        return {"status": "BLOCKED", "reason": str(exc), "artifact_refs": (diagnostic,),
                "evidence_refs": (f"dataset-sha256:{_digest(data)}",),
                "verification_refs": ("locked_dataset", "IS_candidate_lineage"), "provenance": PROVENANCE}

    locked = None
    locked_path = root / LOCKED_BASELINE
    if locked_path.is_file():
        try:
            locked = json.loads(locked_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            locked = None

    generated_candidates = root / "research" / ".aios_locked_candidates.json"
    generated_candidates.parent.mkdir(parents=True, exist_ok=True)
    generated_candidates.write_text(json.dumps(candidates, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cmd = [sys.executable, "run_research_pipeline.py", "--data", str(DATASET),
           "--candidates", str(generated_candidates.relative_to(root)), "--out", str(RESULT),
           "--objective", "profit_factor", "--validation-min-pf", "1.0", "--validation-min-return", "0.0"]
    proc = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=600, check=False)
    if proc.returncode != 0 or not result_path.is_file():
        diagnostic = _record_failure(root, "final_is_validation_oos_pipeline",
                                     f"pipeline exited {proc.returncode}", stdout=proc.stdout, stderr=proc.stderr)
        return {"status": "BLOCKED", "reason": "IS-validation-OOS pipeline failed",
                "evidence_refs": (f"dataset-sha256:{_digest(data)}",),
                "verification_refs": ("research_pipeline",), "artifact_refs": (diagnostic,),
                "provenance": PROVENANCE}

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if locked is not None:
        if payload.get("dataset", {}).get("sha256") != locked.get("dataset", {}).get("sha256"):
            return {"status": "BLOCKED", "reason": "recomputed dataset digest differs from locked research report",
                    "artifact_refs": (str(RESULT), str(LOCKED_BASELINE)),
                    "evidence_refs": (f"dataset-sha256:{_digest(data)}", f"result-sha256:{_digest(result_path)}"),
                    "verification_refs": ("locked_dataset", "artifact_lineage"), "provenance": PROVENANCE}
        if payload.get("selected_config") != locked.get("selected_config"):
            return {"status": "BLOCKED", "reason": "recomputed IS selection differs from locked research report",
                    "artifact_refs": (str(RESULT), str(LOCKED_BASELINE)),
                    "evidence_refs": (f"dataset-sha256:{_digest(data)}", f"result-sha256:{_digest(result_path)}"),
                    "verification_refs": ("IS_selection", "artifact_lineage"), "provenance": PROVENANCE}

    validation = payload.get("validation") or {}
    oos = payload.get("oos")
    evidence = (f"dataset-sha256:{_digest(data)}", f"result-sha256:{_digest(result_path)}")
    verification = ("IS", "validation_gate", "OOS", "locked_dataset", "provenance")
    if not validation.get("passed") or oos is None:
        return {"status": "BLOCKED", "reason": "validation gate did not pass; OOS was correctly not evaluated",
                "artifact_refs": (str(RESULT), str(candidate_source)),
                "evidence_refs": evidence,
                "verification_refs": verification, "provenance": PROVENANCE,
                "validation": validation.get("result", {}).get("metrics")}

    metrics = oos.get("metrics", {})
    return {"status": "PASS", "problem": problem, "artifact_refs": (str(RESULT), str(candidate_source)),
            "evidence_refs": evidence, "verification_refs": verification, "provenance": PROVENANCE,
            "metrics": {k: metrics.get(k) for k in ("total_return", "profit_factor", "max_drawdown", "win_rate", "trades")},
            "selected_config": payload.get("selected_config")}


if __name__ == "__main__":
    print(json.dumps(execute(problem="AIOS final research workload"), indent=2))
