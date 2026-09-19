#!/usr/bin/env python3
"""Strict BC3 fast gate; no fabricated performance evidence."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def canonical_hash(candidate: dict) -> str:
    payload = dict(candidate)
    payload.pop("candidate_hash", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finite_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_metrics(metrics: dict) -> bool:
    required = {
        "trade_count",
        "win_count",
        "loss_count",
        "win_rate",
        "total_return",
        "avg_return",
        "profit_factor",
        "max_drawdown",
    }
    if not required.issubset(metrics):
        return False
    if any(not _finite_number(metrics[k]) for k in required):
        return False

    tc = int(metrics["trade_count"])
    wc = int(metrics["win_count"])
    lc = int(metrics["loss_count"])
    if tc < 0 or wc < 0 or lc < 0 or wc + lc != tc:
        return False

    expected_wr = 0.0 if tc == 0 else wc / tc
    return math.isclose(
        float(metrics["win_rate"]),
        expected_wr,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def validate_gate3(candidate: dict, evidence: dict):
    required = {
        "bc",
        "parent_bc",
        "hypothesis_id",
        "conceptual_change",
        "evidence_sources",
        "rationale",
        "is_testable",
        "oos_selection_used",
        "candidate_hash",
    }
    if not required.issubset(candidate):
        return False, "candidate_fields_missing"
    if candidate["bc"] != 3 or candidate["parent_bc"] != 2:
        return False, "bc_parent_mismatch"
    if candidate["is_testable"] is not True:
        return False, "candidate_not_testable"
    if candidate["oos_selection_used"] is not False:
        return False, "candidate_oos_selection_forbidden"

    from engine.hypotheses import HYPOTHESES

    if (
        candidate["hypothesis_id"] not in HYPOTHESES
        and candidate["hypothesis_id"] not in {"mechanism_family", "discovered_primitive"}
    ):
        return False, "unexecutable_hypothesis_id"

    if candidate["candidate_hash"] != canonical_hash(candidate):
        return False, "candidate_hash_mismatch"

    required_e = {
        "schema_version",
        "bc",
        "parent_bc",
        "hypothesis_id",
        "candidate_hash",
        "oos_selection_used",
        "oos_executed",
        "validation_passed",
        "gross_validation_passed",
        "validation_basis",
        "net_validation_gate",
        "dataset",
        "VALIDATION",
    }
    if not required_e.issubset(evidence):
        return False, "evidence_fields_missing"
    if evidence["schema_version"] < 10:
        return False, "evidence_schema_too_old"
    if evidence["bc"] != 3 or evidence["parent_bc"] != 2:
        return False, "evidence_identity_invalid"
    if evidence["hypothesis_id"] != candidate["hypothesis_id"]:
        return False, "hypothesis_identity_mismatch"
    if evidence["candidate_hash"] != candidate["candidate_hash"]:
        return False, "candidate_hash_mismatch"
    if evidence["oos_selection_used"] is not False:
        return False, "oos_selection_forbidden"
    if evidence["oos_executed"] is not False:
        return False, "oos_execution_forbidden"
    if evidence["validation_basis"] != "NET_REQUIRED_FOR_PROMOTION":
        return False, "validation_basis_invalid"

    dataset = evidence["dataset"]
    if (
        not isinstance(dataset, dict)
        or not isinstance(dataset.get("sha256"), str)
        or len(dataset["sha256"]) != 64
    ):
        return False, "dataset_identity_missing"

    validation = evidence["VALIDATION"]
    if not isinstance(validation, dict) or not isinstance(validation.get("metrics"), dict):
        return False, "validation_metrics_missing"

    metrics = validation["metrics"]
    if not _validate_metrics(metrics):
        return False, "validation_metrics_invalid"

    from research.validation_policy import EVALUATION_SPEC, validation_gate

    quality_passed, _ = validation_gate(metrics)
    expected_net = (
        EVALUATION_SPEC.get("cost_model_status") == "AVAILABLE"
        and quality_passed
    )
    if bool(evidence["validation_passed"]) != expected_net:
        return False, "validation_gate_inconsistent"
    if bool(evidence["gross_validation_passed"]) != quality_passed:
        return False, "gross_validation_gate_inconsistent"

    expected_state = "PASS" if expected_net else "VALIDATION_QUALITY_FAILED"
    if evidence["net_validation_gate"] != expected_state:
        return False, "net_validation_gate_inconsistent"
    if not expected_net:
        return False, "validation_not_promotable"

    return True, "PROMOTE_TO_FUTURE_OOS_TEST"


def main() -> int:
    candidate_path = ROOT / "research" / "autonomous_candidates" / "BC3.json"
    evidence_path = ROOT / "research" / "bc3_validation_result.json"

    if not candidate_path.exists():
        raise SystemExit("BLOCKED: BC3 candidate artifact missing")
    if not evidence_path.exists():
        raise SystemExit("BLOCKED: BC3 validation evidence missing")

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    ok, reason = validate_gate3(candidate, evidence)
    if ok:
        print("BC3_VALIDATION_PASS")
        print("PROMOTE_TO_FUTURE_OOS_TEST")
        return 0

    print(f"BC3_VALIDATION_FAIL reason={reason}")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
