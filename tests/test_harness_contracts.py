import pytest
from research.contracts import canonical_hash, transition, validate_candidate, validate_evaluation


def candidate():
    c = {"schema_version": 1, "bc": 2, "parent_bc": 1, "hypothesis_id": "H_TEST"}
    c["candidate_hash"] = canonical_hash(c)
    return c


def test_candidate_hash_is_required_and_verified():
    c = candidate()
    validate_candidate(c)
    c["hypothesis_id"] = "H_CHANGED"
    with pytest.raises(ValueError, match="CANDIDATE_HASH_MISMATCH"):
        validate_candidate(c)


def test_evaluation_cannot_claim_oos_execution():
    c = candidate()
    e = {"schema_version": 1, "bc": 2, "parent_bc": 1, "hypothesis_id": "H_TEST", "candidate_hash": c["candidate_hash"], "dataset": {}, "IS": {}, "VALIDATION": {}, "oos_selection_used": True, "oos_executed": False}
    with pytest.raises(ValueError, match="EVALUATION_OOS_CONTAMINATION"):
        validate_evaluation(e, c)


def test_transition_rejects_duplicate_bc():
    s = {"history": [], "next_bc": 2}
    s = transition(s, "REJECT_BC", 2, "hash")
    with pytest.raises(ValueError, match="TRANSITION_DUPLICATE_BC"):
        transition(s, "REJECT_BC", 2, "hash")
