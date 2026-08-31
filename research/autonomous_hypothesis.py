"""Strict validation for hypotheses produced by the research agent.

The agent may propose a hypothesis, but this module is the authority that decides
whether it is admissible. It never reads OOS results and never changes criteria.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REQUIRED = {
    "bc", "parent_bc", "hypothesis_id", "conceptual_change", "evidence_sources",
    "rationale", "is_testable", "oos_selection_used",
}


def canonical_hash(candidate: dict) -> str:
    payload = {k: candidate[k] for k in sorted(candidate) if k != "candidate_hash"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_candidate(candidate: dict, expected_bc: int, expected_parent: int) -> tuple[bool, str]:
    missing = sorted(REQUIRED - candidate.keys())
    if missing:
        return False, f"missing_fields:{','.join(missing)}"
    if candidate["bc"] != expected_bc or candidate["parent_bc"] != expected_parent:
        return False, "bc_parent_mismatch"
    change = candidate["conceptual_change"]
    if isinstance(change, list) or not isinstance(change, str) or not change.strip():
        return False, "exactly_one_conceptual_change_required"
    sources = candidate["evidence_sources"]
    if not isinstance(sources, list) or not sources or any(not isinstance(x, str) or not x.strip() for x in sources):
        return False, "evidence_sources_required"
    if candidate["oos_selection_used"] is not False:
        return False, "oos_selection_forbidden"
    if candidate["is_testable"] is not True:
        return False, "not_testable"
    supplied = candidate.get("candidate_hash")
    expected = canonical_hash(candidate)
    if supplied is not None and supplied != expected:
        return False, "candidate_hash_mismatch"
    candidate["candidate_hash"] = expected
    return True, expected


def load_candidate(path: Path, expected_bc: int, expected_parent: int) -> dict:
    candidate = json.loads(path.read_text(encoding="utf-8"))
    ok, reason = validate_candidate(candidate, expected_bc, expected_parent)
    if not ok:
        raise ValueError(reason)
    return candidate


def write_candidate(path: Path, candidate: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
