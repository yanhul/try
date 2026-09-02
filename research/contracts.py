from __future__ import annotations

"""Strict, deterministic contracts for autonomous research artifacts."""

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DECISIONS = {"REJECT_BC", "PROMOTE_TO_FUTURE_OOS_TEST"}


def canonical_hash(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("candidate_hash", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_keys(obj: dict[str, Any], keys: tuple[str, ...], kind: str) -> None:
    missing = [k for k in keys if k not in obj]
    if missing:
        raise ValueError(f"{kind}_MISSING_KEYS:{','.join(missing)}")


def validate_candidate(candidate: dict[str, Any]) -> None:
    require_keys(candidate, ("schema_version", "bc", "parent_bc", "hypothesis_id", "candidate_hash"), "CANDIDATE")
    if candidate["schema_version"] != SCHEMA_VERSION:
        raise ValueError("CANDIDATE_SCHEMA_VERSION")
    if int(candidate["bc"]) != int(candidate["parent_bc"]) + 1:
        raise ValueError("CANDIDATE_PARENT_SEQUENCE")
    if candidate["candidate_hash"] != canonical_hash(candidate):
        raise ValueError("CANDIDATE_HASH_MISMATCH")


def validate_evaluation(evidence: dict[str, Any], candidate: dict[str, Any]) -> None:
    require_keys(evidence, ("schema_version", "bc", "parent_bc", "hypothesis_id", "candidate_hash", "dataset", "IS", "VALIDATION"), "EVALUATION")
    if evidence["schema_version"] != SCHEMA_VERSION:
        raise ValueError("EVALUATION_SCHEMA_VERSION")
    for key in ("bc", "parent_bc", "hypothesis_id", "candidate_hash"):
        if evidence[key] != candidate[key]:
            raise ValueError(f"EVALUATION_IDENTITY_MISMATCH:{key}")
    if evidence.get("oos_selection_used") is True or evidence.get("oos_executed") is True:
        raise ValueError("EVALUATION_OOS_CONTAMINATION")


def validate_decision(decision: dict[str, Any], candidate: dict[str, Any], evidence: dict[str, Any]) -> None:
    require_keys(decision, ("schema_version", "bc", "candidate_hash", "decision", "evidence_hash"), "DECISION")
    if decision["schema_version"] != SCHEMA_VERSION:
        raise ValueError("DECISION_MISSING_KEYS") if False else None
    if decision["schema_version"] != SCHEMA_VERSION:
        raise ValueError("DECISION_SCHEMA_VERSION")
    if decision["bc"] != candidate["bc"] or decision["candidate_hash"] != candidate["candidate_hash"]:
        raise ValueError("DECISION_IDENTITY_MISMATCH")
    if decision["decision"] not in DECISIONS:
        raise ValueError("DECISION_UNKNOWN")
    if decision["evidence_hash"] != canonical_hash(evidence):
        raise ValueError("DECISION_EVIDENCE_HASH_MISMATCH")


def transition(state: dict[str, Any], decision: str, bc: int, candidate_hash: str) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError("TRANSITION_UNKNOWN_DECISION")
    history = list(state.get("history", []))
    if any(int(x.get("bc", -1)) == int(bc) for x in history):
        raise ValueError(f"TRANSITION_DUPLICATE_BC:{bc}")
    expected = int(state.get("next_bc", 1))
    if bc != expected:
        raise ValueError(f"TRANSITION_UNEXPECTED_BC:{bc}:{expected}")
    history.append({"bc": bc, "decision": decision, "candidate_hash": candidate_hash})
    state = dict(state)
    state["history"] = history
    state["last_bc"] = bc
    state["next_bc"] = bc + 1
    return state
