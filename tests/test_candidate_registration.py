import json
from pathlib import Path

import pytest

from research import candidate_registration, lineage_engine
from research.autonomous_hypothesis import canonical_hash
from research.hypothesis_novelty import novelty_metadata


SOURCE = "https://github.com/example/vwap-source"


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture
def durable_case(monkeypatch, tmp_path):
    research = tmp_path / "research"
    lineage_path = research / "lineage.jsonl"
    monkeypatch.setattr(lineage_engine, "LOG", lineage_path)

    parent_hash = "b" * 64
    parent_candidate = {
        "bc": 2,
        "parent_bc": 1,
        "hypothesis_id": "mechanism_family",
        "candidate_hash": parent_hash,
        "conceptual_change": "parent mechanism",
        "evidence_sources": ["https://github.com/example/parent"],
        "discovery_spec": {"mechanism_family": "momentum_trend", "threshold": 0.001, "direction": "below"},
        "oos_selection_used": False,
    }
    candidate = {
        "bc": 3,
        "parent_bc": 2,
        "hypothesis_id": "mechanism_family",
        "conceptual_change": "Translate one selected VWAP mechanism into a single executable BTC 1H predicate.",
        "evidence_sources": [SOURCE],
        "rationale": "A pre-registered, testable structural hypothesis; no performance claim.",
        "is_testable": True,
        "oos_selection_used": False,
        "discovery_spec": {"mechanism_family": "vwap_volume_profile", "threshold": 0.0, "direction": "above"},
    }
    candidate.update(novelty_metadata(candidate))
    candidate["candidate_hash"] = canonical_hash(candidate)

    _write(research / "campaign_policy.json", {
        "campaign_id": "TEST-CAMPAIGN",
        "max_screening_candidates": 100,
        "controller_batch_size": 1,
        "terminal_outcomes": ["EDGE_FOUND", "NO_EDGE_FOUND", "INCONCLUSIVE"],
        "promotion_requires": "IS_VALIDATION",
    })
    _write(research / "bc_lifecycle_state.json", {
        "campaign_id": "TEST-CAMPAIGN",
        "campaign_terminal": False,
        "terminal": False,
        "current_bc": 3,
        "next_bc": 3,
        "last_bc": 2,
        "checkpoint_seq": 7,
        "phase": "PERSISTED",
        "history": [{"bc": 2, "decision": "REJECT_BC", "candidate_hash": parent_hash}],
    })
    _write(research / "autonomous_candidates" / "BC2.json", parent_candidate)
    _write(research / "failure_analysis" / "BC2.json", {
        "bc": 2, "parent_bc": 1, "decision": "REJECT", "reason": "VALIDATION_FAILED",
        "candidate_hash": parent_hash, "oos_selection_used": False,
    })
    _write(research / "bc2_validation_result.json", {
        "bc": 2, "candidate_hash": parent_hash, "oos_executed": False,
        "oos_selection_used": False, "dataset": {"sha256": "a" * 64},
    })
    _write(research / "autonomous_candidates" / "BC3.json", candidate)
    _write(research / "bc_queue.json", [candidate])
    _write(research / "discovery" / ".search_memory.json", {
        "schema_version": 1, "candidates": {}, "last_selected_family": "vwap_volume_profile",
        "last_selection_bc": 3,
    })
    _write(research / "discovery" / "survivors.json", {
        "schema_version": 4,
        "survivors": [{"candidate_id": "survivor-1", "family": "vwap_volume_profile", "source_url": SOURCE}],
    })
    return tmp_path, candidate, parent_hash, lineage_path


def test_registration_requires_matching_candidate_parent_failure_family_novelty_and_lineage(durable_case):
    root, candidate, parent_hash, lineage_path = durable_case
    assert candidate_registration.register_candidate_lineage(root) == "REGISTERED"
    records = [json.loads(line) for line in lineage_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    record = records[0]
    assert record["registration_type"] == "CANDIDATE_REGISTRATION"
    assert record["generation"] == 3
    assert record["config_hash"] == candidate["candidate_hash"]
    assert record["result"]["parent_failure_decision"] == "REJECT"
    assert record["result"]["selected_survivor_id"] == "survivor-1"
    assert record["novelty_key"] == candidate["novelty_key"]
    assert candidate_registration.validate_queued_candidate(root, require_registration=True)["registered"] is True
    assert candidate_registration.register_candidate_lineage(root) == "ALREADY_REGISTERED"


def test_selected_family_mismatch_blocks_registration(durable_case):
    root, _, _, _ = durable_case
    memory = json.loads((root / "research/discovery/.search_memory.json").read_text())
    memory["last_selected_family"] = "fvg_imbalance"
    _write(root / "research/discovery/.search_memory.json", memory)
    with pytest.raises(ValueError, match="SELECTED_FAMILY_MISMATCH"):
        candidate_registration.register_candidate_lineage(root)


def test_prior_novelty_replay_blocks_registration(durable_case):
    root, candidate, _, _ = durable_case
    prior = dict(candidate)
    prior["bc"] = 1
    prior["parent_bc"] = 0
    prior["candidate_hash"] = "c" * 64
    _write(root / "research/autonomous_candidates/BC1.json", prior)
    with pytest.raises(ValueError, match="NOVELTY_REPLAY"):
        candidate_registration.register_candidate_lineage(root)


def test_missing_parent_failure_blocks_registration(durable_case):
    root, _, _, _ = durable_case
    (root / "research/failure_analysis/BC2.json").unlink()
    with pytest.raises(ValueError, match="PARENT_EVIDENCE_MISSING"):
        candidate_registration.register_candidate_lineage(root)


def test_evaluation_artifact_before_registration_blocks_authorization(durable_case):
    root, _, _, _ = durable_case
    _write(root / "research/bc3_validation_result.json", {"bc": 3})
    with pytest.raises(ValueError, match="EVALUATION_PRECEDED_REGISTRATION"):
        candidate_registration.validate_queued_candidate(root, require_registration=False)


def test_pending_intent_requires_registration_lineage(durable_case):
    root, _, _, _ = durable_case
    with pytest.raises(ValueError, match="REGISTRATION_LINEAGE_MISSING"):
        candidate_registration.authorize_pending(root, source_run_id=123, kind="PROGRESS", require_main=False)


def test_pending_intent_binds_current_checkpoint_only_after_registration(durable_case):
    root, candidate, _, _ = durable_case
    candidate_registration.register_candidate_lineage(root)
    intent = candidate_registration.authorize_pending(root, source_run_id=123, kind="PROGRESS", require_main=False)
    assert intent["status"] == "PENDING"
    assert intent["created_by_run_id"] == 123
    assert intent["checkpoint_seq"] == 7
    assert intent["candidate_hash"] == candidate["candidate_hash"]
    persisted = json.loads((root / "research/continuation_intent.json").read_text())
    assert persisted == intent
