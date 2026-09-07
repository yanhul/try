"""Deterministic lifecycle contracts for the autonomous research controller.

These contracts are normative runtime checks. They do not choose hypotheses,
change evaluation criteria, or grant promotion authority.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy


_REQUIRED_CANDIDATE = {
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
_REQUIRED_EVALUATION = {
    "schema_version",
    "bc",
    "parent_bc",
    "hypothesis_id",
    "candidate_hash",
    "oos_selection_used",
    "oos_executed",
    "dataset",
    "evaluation_spec",
    "IS",
    "VALIDATION",
    "validation_passed",
}
_TERMINAL_DECISIONS = {"PROMOTE_TO_FUTURE_OOS_TEST"}
_REJECT_DECISION = "REJECT_BC"


def _canonical_candidate_hash(candidate: dict) -> str:
    payload = {k: candidate[k] for k in sorted(candidate) if k != "candidate_hash"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def validate_candidate(candidate: dict) -> dict:
    """Validate an already materialized candidate and return a defensive copy."""
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object")
    missing = sorted(_REQUIRED_CANDIDATE - candidate.keys())
    if missing:
        raise ValueError(f"candidate missing fields: {','.join(missing)}")
    if not isinstance(candidate["bc"], int) or not isinstance(candidate["parent_bc"], int):
        raise ValueError("candidate bc fields must be integers")
    if candidate["bc"] != candidate["parent_bc"] + 1:
        raise ValueError("candidate bc_parent_sequence_invalid")
    if not isinstance(candidate["hypothesis_id"], str) or not candidate["hypothesis_id"].strip():
        raise ValueError("candidate hypothesis_id required")
    if not isinstance(candidate["conceptual_change"], str) or not candidate["conceptual_change"].strip():
        raise ValueError("candidate conceptual_change required")
    if not isinstance(candidate["rationale"], str) or not candidate["rationale"].strip():
        raise ValueError("candidate rationale required")
    if not isinstance(candidate["evidence_sources"], list) or not candidate["evidence_sources"]:
        raise ValueError("candidate evidence_sources required")
    if any(not isinstance(x, str) or not x.strip() for x in candidate["evidence_sources"]):
        raise ValueError("candidate evidence_sources must contain strings")
    if candidate["is_testable"] is not True:
        raise ValueError("candidate must be testable")
    if candidate["oos_selection_used"] is not False:
        raise ValueError("candidate oos selection forbidden")
    expected_hash = _canonical_candidate_hash(candidate)
    if candidate["candidate_hash"] != expected_hash:
        raise ValueError("candidate_hash_mismatch")
    return deepcopy(candidate)


def _require_metrics(result: object, label: str) -> None:
    if not isinstance(result, dict) or not isinstance(result.get("metrics"), dict):
        raise ValueError(f"evaluation {label} metrics missing")


def validate_evaluation(evaluation: dict, candidate: dict) -> dict:
    """Validate evaluator output against the exact candidate identity and split contract."""
    candidate = validate_candidate(candidate)
    if not isinstance(evaluation, dict):
        raise ValueError("evaluation must be an object")
    missing = sorted(_REQUIRED_EVALUATION - evaluation.keys())
    if missing:
        raise ValueError(f"evaluation missing fields: {','.join(missing)}")
    if evaluation["schema_version"] != 1:
        raise ValueError("unsupported evaluation schema")
    for field in ("bc", "parent_bc", "hypothesis_id", "candidate_hash"):
        if evaluation[field] != candidate[field]:
            raise ValueError(f"evaluation {field} mismatch")
    if evaluation["oos_selection_used"] is not False or evaluation["oos_executed"] is not False:
        raise ValueError("evaluation oos contamination")
    dataset = evaluation["dataset"]
    if not isinstance(dataset, dict) or not isinstance(dataset.get("sha256"), str) or not dataset["sha256"].strip():
        raise ValueError("evaluation dataset hash missing")
    spec = evaluation["evaluation_spec"]
    if not isinstance(spec, dict):
        raise ValueError("evaluation spec missing")
    for key in ("stop_fraction", "reward_multiple", "round_trip_cost"):
        if key not in spec:
            raise ValueError(f"evaluation spec missing:{key}")
    _require_metrics(evaluation["IS"], "IS")
    _require_metrics(evaluation["VALIDATION"], "VALIDATION")
    if not isinstance(evaluation["validation_passed"], bool):
        raise ValueError("evaluation validation_passed must be boolean")
    return deepcopy(evaluation)


def transition(state: dict, decision: str, bc: int, candidate_hash: str) -> dict:
    """Apply one deterministic BC lifecycle transition to a defensive state copy."""
    if not isinstance(state, dict):
        raise ValueError("state must be an object")
    if decision not in _TERMINAL_DECISIONS | {_REJECT_DECISION}:
        raise ValueError("unsupported lifecycle decision")
    if not isinstance(bc, int) or not isinstance(candidate_hash, str) or not candidate_hash.strip():
        raise ValueError("transition identity invalid")
    current = state.get("current_bc")
    last_bc = state.get("last_bc")
    next_bc = state.get("next_bc")
    if current is not None and not isinstance(current, int):
        raise ValueError("state current_bc invalid")
    if last_bc is not None and not isinstance(last_bc, int):
        raise ValueError("state last_bc invalid")
    if not isinstance(next_bc, int):
        raise ValueError("state next_bc invalid")
    if next_bc != bc:
        raise ValueError("transition out_of_sequence")
    if last_bc is not None and bc != last_bc + 1:
        raise ValueError("transition duplicate_or_out_of_sequence")
    if current is not None and current not in (last_bc, bc):
        raise ValueError("transition current_bc mismatch")
    history = state.get("history", [])
    if not isinstance(history, list):
        raise ValueError("state history invalid")
    if any(isinstance(x, dict) and x.get("bc") == bc for x in history):
        raise ValueError("transition duplicate_bc")

    out = deepcopy(state)
    out["last_bc"] = bc
    out["current_bc"] = bc
    out["next_bc"] = bc + 1
    out.setdefault("history", []).append(
        {"bc": bc, "candidate_hash": candidate_hash, "decision": decision}
    )
    if decision == "PROMOTE_TO_FUTURE_OOS_TEST":
        out["terminal"] = False
        out["phase"] = "FREEZE_OOS"
    else:
        out["terminal"] = False
        out["phase"] = "PERSISTED"
    return out


__all__ = ["validate_candidate", "validate_evaluation", "transition"]
