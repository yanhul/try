#!/usr/bin/env python3
"""Repair durable evidence lost by an interrupted/legacy campaign persist.

This never executes OOS and never invents research results. It only reconstructs
an integrity receipt from an already persisted BC*_oos_result.json, then restores
the candidate-level failure artifact when the result proves OOS_FAIL.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "research" / "bc_lifecycle_state.json"
CANDIDATES = ROOT / "research" / "autonomous_candidates"
OOS = ROOT / "research" / "oos"
FAILURES = ROOT / "research" / "failure_analysis"


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repair_bc(bc: int) -> bool:
    candidate_path = CANDIDATES / f"BC{bc}.json"
    result_path = OOS / f"BC{bc}_oos_result.json"
    receipt_path = OOS / f"BC{bc}_oos_result_receipt.json"
    failure_path = FAILURES / f"BC{bc}.json"
    candidate = load(candidate_path, {})
    result = load(result_path, {})
    if not candidate or not result:
        return False
    candidate_hash = candidate.get("candidate_hash")
    if not candidate_hash or result.get("bc") != bc or result.get("candidate_hash") != candidate_hash:
        return False
    if result.get("oos_executed") is not True or result.get("oos_selection_used") is not False:
        return False
    if result.get("oos_passed") is not False:
        return False

    result_sha = sha256(result_path)
    if receipt_path.exists():
        receipt = load(receipt_path, {})
        if receipt.get("result_sha256") != result_sha:
            return False
        print(f"OOS_EVIDENCE_RECEIPT_VALID BC{bc}")
    else:
        dataset_sha = result.get("dataset", {}).get("sha256")
        protocol_sha = result.get("protocol_sha256")
        if not dataset_sha or not protocol_sha or not isinstance(result.get("metrics"), dict):
            return False
        receipt_payload = {
            "schema_version": 1,
            "receipt_type": "OOS_EXECUTION_RECEIPT",
            "bc": bc,
            "candidate_hash": candidate_hash,
            "result_sha256": result_sha,
            "dataset_sha256": dataset_sha,
            "protocol_sha256": protocol_sha,
            "split": result.get("split"),
            "oos_selection_used": False,
            "oos_executed": True,
            "oos_passed": False,
            "metrics": result["metrics"],
            "predicate": result.get("predicate"),
            "reconstructed_from_durable_result": True,
        }
        OOS.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"OOS_EVIDENCE_RECEIPT_RECONSTRUCTED BC{bc} result_sha256={result_sha}")

    FAILURES.mkdir(parents=True, exist_ok=True)
    if not failure_path.exists():
        payload = {
            "bc": bc,
            "parent_bc": int(candidate.get("parent_bc", bc - 1)),
            "decision": "REJECT",
            "reason": "OOS_FAILED",
            "hypothesis_id": candidate.get("hypothesis_id"),
            "candidate_hash": candidate_hash,
            "conceptual_change": candidate.get("conceptual_change"),
            "evidence_sources": candidate.get("evidence_sources"),
            "validation_summary": result.get("metrics"),
            "oos_verdict": "OOS_FAIL",
            "oos_selection_used": False,
            "action": "reject candidate and require a distinct next hypothesis",
            "repair": "restored from durable OOS result; no research evidence fabricated",
        }
        failure_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"FAILURE_ANALYSIS_RESTORED BC{bc}")
    return True


def main() -> int:
    state = load(STATE, {})
    if not state:
        return 0
    reason = state.get("campaign_terminal_reason")
    if reason not in {"OOS_FAIL", "OOS_FAIL_MIGRATED_TO_CANDIDATE_REJECTION"}:
        print("OOS_EVIDENCE_REPAIR_NOT_REQUIRED")
        return 0
    bc = int(state.get("current_bc") or state.get("last_bc") or 0)
    if not bc:
        print("OOS_EVIDENCE_REPAIR_HOLD missing_bc")
        return 1
    if repair_bc(bc):
        return 0
    print(f"OOS_EVIDENCE_REPAIR_HOLD BC{bc} reason=INSUFFICIENT_DURABLE_EVIDENCE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
