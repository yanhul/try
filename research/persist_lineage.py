#!/usr/bin/env python3
"""Persist one completed controller iteration into the append-only lineage log.

This is provenance only. It cannot change policy, evaluator, promotion criteria,
validation/OOS boundaries, iteration budgets, or terminal conditions.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from research.lineage_engine import append_experiment, read_lineage
from research.oos_lifecycle import assert_history_entry_legal

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "research" / "bc_lifecycle_state.json"
CANDIDATES = ROOT / "research" / "autonomous_candidates"
VALIDATION = ROOT / "research"
DATA = ROOT / "data" / "BTCUSDT_1h.csv"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "MISSING"


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def main() -> int:
    state = load(STATE, {})
    bc = state.get("last_bc")
    if bc is None:
        print("LINEAGE_SKIP no completed BC")
        return 0
    candidate_path = CANDIDATES / f"BC{int(bc)}.json"
    candidate = load(candidate_path, {})
    if not candidate:
        print(f"LINEAGE_SKIP missing candidate BC{bc}")
        return 0

    experiment_id = f"BC{int(bc)}:{candidate.get('candidate_hash', candidate.get('hypothesis_id', 'unknown'))}"
    if any(str(x.get("experiment_id")) == experiment_id for x in read_lineage()):
        print(f"LINEAGE_EXISTS {experiment_id}")
        return 0

    history = [x for x in state.get("history", []) if int(x.get("bc", -1)) == int(bc)]
    latest = history[-1] if history else {}
    for entry in history:
        assert_history_entry_legal(entry)
    oos_evaluation = state.get("oos_evaluation") or {}
    if oos_evaluation and oos_evaluation.get("bc") == int(bc):
        assert_history_entry_legal(oos_evaluation)
        if oos_evaluation.get("candidate_hash") != candidate.get("candidate_hash"):
            raise ValueError("OOS_EVALUATION_BINDING_MISMATCH")
    validation_path = VALIDATION / f"bc{int(bc)}_validation_result.json"
    validation = load(validation_path, {})
    result = validation if validation else latest
    verdict = oos_evaluation.get("oos_verdict") if oos_evaluation.get("oos_verdict") in {"OOS_PASS","OOS_FAIL"} else "UNKNOWN"
    record = {
        "experiment_id": experiment_id,
        "generation": int(bc),
        "parent_artifacts": [f"research/failure_analysis/BC{int(bc)-1}.json"],
        "hypothesis": candidate.get("hypothesis", candidate.get("hypothesis_id", "UNKNOWN")),
        "change": candidate.get("change", candidate.get("description", "UNKNOWN")),
        "code_revision": state.get("code_revision", "workflow-main"),
        "config_hash": candidate.get("candidate_hash", "UNKNOWN"),
        "data_hash": sha256_file(DATA),
        "evaluator": "engine.autonomous_evaluator + registered BC gate",
        "result": result,
        "verdict": verdict,
        "decision": latest.get("decision", "UNKNOWN"),
        "evidence": [str(validation_path.relative_to(ROOT))] if validation_path.exists() else [],
        "findings": latest.get("findings", []),
        "constraints": latest.get("constraints", []),
        "claims": latest.get("claims", []),
    }
    append_experiment(record)
    print(f"LINEAGE_RECORDED {experiment_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
