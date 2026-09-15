import pytest

from research.astra_bridge import materialize_research_candidate, proposal_record, propose_from_research_candidate
from research.autonomous_hypothesis import canonical_hash


def parent_candidate():
    candidate = {
        "bc": 10,
        "parent_bc": 9,
        "hypothesis_id": "discovered_primitive",
        "conceptual_change": "baseline threshold",
        "evidence_sources": ["source:test"],
        "rationale": "bounded test",
        "is_testable": True,
        "oos_selection_used": False,
        "discovery_spec": {
            "operator": "rank",
            "left": "volume",
            "window": 20,
            "threshold": 0.8,
            "direction": "above",
        },
    }
    candidate["candidate_hash"] = canonical_hash(candidate)
    return candidate


def test_bridge_mutates_only_executable_search_spec():
    parent = parent_candidate()
    proposal = propose_from_research_candidate(parent, {"reason": "OOS_FAILED"})
    assert proposal.parent_research_hash == parent["candidate_hash"]
    assert proposal.config.keys() == {"candidate_spec"}
    assert proposal.mutation["field"] in {"threshold", "window"}
    assert proposal.astra_candidate_id != proposal.astra_parent_id


def test_bridge_materializes_strict_research_candidate():
    parent = parent_candidate()
    proposal = propose_from_research_candidate(parent, {"reason": "OOS_FAILED"})
    child = materialize_research_candidate(parent, proposal, bc=11)
    assert child["bc"] == 11
    assert child["parent_bc"] == 10
    assert child["oos_selection_used"] is False
    assert child["candidate_hash"] == canonical_hash(child)
    assert any(x.startswith("astra:") for x in child["evidence_sources"])


def test_bridge_never_mutates_parent_or_accepts_unknown_fields():
    parent = parent_candidate()
    before = parent.copy()
    proposal = propose_from_research_candidate(parent, {"reason": "OOS_FAILED"})
    assert parent == before
    assert set(proposal.config) == {"candidate_spec"}
    with pytest.raises(ValueError):
        propose_from_research_candidate({**parent, "candidate_hash": "bad"}, {})


def test_bridge_frontier_is_deterministic_and_skips_used():
    parent = parent_candidate()
    first = propose_from_research_candidate(parent, {"reason": "OOS_FAILED"})
    second = propose_from_research_candidate(parent, {"reason": "OOS_FAILED"}, used_ids={first.astra_candidate_id})
    assert first.astra_candidate_id != second.astra_candidate_id
    assert first.mutation["field"] == second.mutation["field"] or first.mutation["value"] != second.mutation["value"]


def test_proposal_record_does_not_claim_evaluation_or_promotion():
    parent = parent_candidate()
    proposal = propose_from_research_candidate(parent, {"reason": "OOS_FAILED"})
    child = materialize_research_candidate(parent, proposal, bc=11)
    record = proposal_record(proposal, child)
    assert record["status"] == "PROPOSED"
    assert "decision" not in record
    assert "oos_receipt" not in record
