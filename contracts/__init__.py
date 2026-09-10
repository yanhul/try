"""Deterministic lifecycle contracts for the autonomous research controller."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

_REQUIRED_CANDIDATE = {"bc", "parent_bc", "hypothesis_id", "conceptual_change", "evidence_sources", "rationale", "is_testable", "oos_selection_used", "candidate_hash"}
_REQUIRED_EVALUATION = {"schema_version", "bc", "parent_bc", "hypothesis_id", "candidate_hash", "oos_selection_used", "oos_executed", "dataset", "evaluation_spec", "IS", "VALIDATION", "validation_passed"}
_DECISIONS = {"PROMOTE_TO_FUTURE_OOS_TEST", "REJECT_BC"}


def _canonical_candidate_hash(candidate: dict) -> str:
    payload = {k: candidate[k] for k in sorted(candidate) if k != "candidate_hash"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_candidate(candidate: dict) -> dict:
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object")
    missing = sorted(_REQUIRED_CANDIDATE - candidate.keys())
    if missing:
        raise ValueError(f"candidate missing fields: {','.join(missing)}")
    if not isinstance(candidate["bc"], int) or not isinstance(candidate["parent_bc"], int):
        raise ValueError("candidate bc fields must be integers")
    if candidate["bc"] != candidate["parent_bc"] + 1:
        raise ValueError("candidate bc_parent_sequence_invalid")
    for field in ("hypothesis_id", "conceptual_change", "rationale"):
        if not isinstance(candidate[field], str) or not candidate[field].strip():
            raise ValueError(f"candidate {field} required")
    if not isinstance(candidate["evidence_sources"], list) or not candidate["evidence_sources"]:
        raise ValueError("candidate evidence_sources required")
    if any(not isinstance(x, str) or not x.strip() for x in candidate["evidence_sources"]):
        raise ValueError("candidate evidence_sources must contain strings")
    if candidate["is_testable"] is not True:
        raise ValueError("candidate must be testable")
    if candidate["oos_selection_used"] is not False:
        raise ValueError("candidate oos selection forbidden")
    if candidate["candidate_hash"] != _canonical_candidate_hash(candidate):
        raise ValueError("candidate_hash_mismatch")
    return deepcopy(candidate)


def _require_metrics(result: object, label: str) -> None:
    if not isinstance(result, dict) or not isinstance(result.get("metrics"), dict):
        raise ValueError(f"evaluation {label} metrics missing")


def validate_evaluation(evaluation: dict, candidate: dict) -> dict:
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
    if not isinstance(state, dict) or decision not in _DECISIONS:
        raise ValueError("invalid lifecycle transition request")
    if not isinstance(bc, int) or not isinstance(candidate_hash, str) or not candidate_hash.strip():
        raise ValueError("transition identity invalid")
    next_bc, last_bc, current_bc = state.get("next_bc"), state.get("last_bc"), state.get("current_bc")
    history = state.get("history", [])
    if not isinstance(next_bc, int) or not isinstance(history, list):
        raise ValueError("state lifecycle fields invalid")
    if any(isinstance(x, dict) and x.get("bc") == bc for x in history):
        raise ValueError("transition duplicate_bc")
    in_progress = last_bc == bc and current_bc == bc and next_bc == bc
    fresh = next_bc == bc and (last_bc is None or bc == last_bc + 1)
    if not (in_progress or fresh):
        raise ValueError("transition out_of_sequence")
    out = deepcopy(state)
    out["last_bc"], out["current_bc"], out["next_bc"] = bc, bc, bc + 1
    out.setdefault("history", []).append({"bc": bc, "candidate_hash": candidate_hash, "decision": decision})
    out["terminal"] = False
    out["phase"] = "FREEZE_OOS" if decision == "PROMOTE_TO_FUTURE_OOS_TEST" else "PERSISTED"
    return out


__all__ = ["validate_candidate", "validate_evaluation", "transition"]
