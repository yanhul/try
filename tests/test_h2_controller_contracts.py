import hashlib
import json

import pytest

from contracts import transition, validate_candidate, validate_evaluation


def candidate():
    value = {
        "bc": 2,
        "parent_bc": 1,
        "hypothesis_id": "H2",
        "conceptual_change": "strict sequence",
        "evidence_sources": ["failure_analysis/BC1.json"],
        "rationale": "test lifecycle contract",
        "is_testable": True,
        "oos_selection_used": False,
    }
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["candidate_hash"] = hashlib.sha256(payload).hexdigest()
    return value


def evaluation(c):
    return {
        "schema_version": 1,
        "bc": c["bc"],
        "parent_bc": c["parent_bc"],
        "hypothesis_id": c["hypothesis_id"],
        "candidate_hash": c["candidate_hash"],
        "oos_selection_used": False,
        "oos_executed": False,
        "dataset": {"sha256": "a" * 64},
        "evaluation_spec": {"stop_fraction": 0.01, "reward_multiple": 2.0, "round_trip_cost": 0.0},
        "IS": {"metrics": {}},
        "VALIDATION": {"metrics": {}},
        "validation_passed": False,
    }


def test_candidate_contract_rejects_hash_tampering():
    c = candidate()
    c["rationale"] = "tampered"
    with pytest.raises(ValueError, match="candidate_hash_mismatch"):
        validate_candidate(c)


def test_evaluation_contract_binds_exact_candidate_and_blocks_oos():
    c = candidate()
    e = evaluation(c)
    assert validate_evaluation(e, c)["candidate_hash"] == c["candidate_hash"]
    e["candidate_hash"] = "bad"
    with pytest.raises(ValueError, match="evaluation candidate_hash mismatch"):
        validate_evaluation(e, c)
    e = evaluation(c)
    e["oos_executed"] = True
    with pytest.raises(ValueError, match="oos contamination"):
        validate_evaluation(e, c)


def test_transition_requires_expected_next_bc_and_is_immutable():
    state = {"history": [], "current_bc": 1, "last_bc": 1, "next_bc": 2, "terminal": False}
    out = transition(state, "REJECT_BC", 2, candidate()["candidate_hash"])
    assert state["next_bc"] == 2
    assert out["next_bc"] == 3
    assert out["history"][-1]["bc"] == 2
    with pytest.raises(ValueError, match="duplicate_bc"):
        transition(out, "REJECT_BC", 2, candidate()["candidate_hash"])


def test_transition_allows_in_progress_bc_without_duplicate_history():
    state = {"history": [], "current_bc": 1, "last_bc": 1, "next_bc": 1, "terminal": False}
    out = transition(state, "REJECT_BC", 1, candidate()["candidate_hash"])
    assert out["next_bc"] == 2
    assert out["history"][0]["bc"] == 1
