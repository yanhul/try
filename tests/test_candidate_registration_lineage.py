import json
from pathlib import Path

import pytest

from research import lineage_engine
from research import register_candidate_lineage as registration
from research.autonomous_hypothesis import canonical_hash


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture
def queued_candidate(monkeypatch, tmp_path):
    root = tmp_path
    research = root / "research"
    candidate_hash = "candidate-hash-477"
    parent_hash = "candidate-hash-476"
    source_url = "https://example.invalid/selected-vwap-source"
    novelty_key = "vwap_volume_profile||||above"
    candidate = {
        "bc": 477,
        "parent_bc": 476,
        "candidate_hash": candidate_hash,
        "hypothesis_id": "mechanism_family",
        "conceptual_change": "Use the selected VWAP/volume-profile family as one testable structural change.",
        "discovery_spec": {
            "mechanism_family": "vwap_volume_profile",
            "direction": "above",
            "threshold": 0.0,
        },
        "evidence_sources": [source_url],
        "novelty_key": novelty_key,
        "novelty_type": "structural_mechanism",
        "parameterization": {"window": None, "threshold": 0.0},
        "is_testable": True,
        "oos_selection_used": False,
    }
    candidate["candidate_hash"] = canonical_hash(candidate)
    candidate_hash = candidate["candidate_hash"]
    state = {
        "campaign_id": "BTCUSDT-1H-AUTONOMOUS-002",
        "current_bc": 477,
        "next_bc": 477,
        "checkpoint_seq": 13767,
        "campaign_terminal": False,
    }
    parent_candidate = {"bc": 476, "candidate_hash": parent_hash, "hypothesis_id": "mechanism_family"}
    failure = {
        "bc": 476,
        "parent_bc": 475,
        "decision": "REJECT",
        "reason": "VALIDATION_FAILED",
        "candidate_hash": parent_hash,
    }
    parent_validation = {
        "bc": 476,
        "candidate_hash": parent_hash,
        "validation_passed": False,
        "oos_executed": False,
        "dataset": {"sha256": "dataset-sha256"},
    }
    survivor = {
        "candidate_id": "selected-vwap-source",
        "family": "vwap_volume_profile",
        "source_url": source_url,
    }
    memory = {
        "last_selection_bc": 477,
        "last_selected_family": "vwap_volume_profile",
        "candidates": {},
    }
    queue_item = {key: candidate.get(key) for key in (
        "bc", "parent_bc", "candidate_hash", "discovery_spec", "novelty_key",
        "evidence_sources", "hypothesis_id",
    )}
    write(research / "bc_lifecycle_state.json", state)
    write(research / "bc_queue.json", [queue_item])
    write(research / "autonomous_candidates/BC477.json", candidate)
    write(research / "autonomous_candidates/BC476.json", parent_candidate)
    write(research / "failure_analysis/BC476.json", failure)
    write(research / "bc476_validation_result.json", parent_validation)
    write(research / "discovery/.search_memory.json", memory)
    write(research / "discovery/survivors.json", {"survivors": [survivor]})
    write(research / "discovery/absorption_proof.json", {
        "absorbed": [{
            "candidate_id": survivor["candidate_id"],
            "family": survivor["family"],
            "source_url": source_url,
            "status": "ABSORBED",
        }],
    })
    write(research / "discovery/implementation_absorption_proof.json", {
        "implemented": [{
            "candidate_id": survivor["candidate_id"],
            "family": survivor["family"],
            "source_url": source_url,
            "status": "IMPLEMENTED",
        }],
    })
    data_path = root / "data/BTCUSDT_1h.csv"
    write(data_path, "timestamp,open,high,low,close,volume\n")

    for name, value in {
        "ROOT": root,
        "STATE": research / "bc_lifecycle_state.json",
        "QUEUE": research / "bc_queue.json",
        "CANDIDATES": research / "autonomous_candidates",
        "FAILURES": research / "failure_analysis",
        "SEARCH_MEMORY": research / "discovery/.search_memory.json",
        "SURVIVORS": research / "discovery/survivors.json",
        "ABSORPTION": research / "discovery/absorption_proof.json",
        "IMPLEMENTATION": research / "discovery/implementation_absorption_proof.json",
        "DATA": data_path,
    }.items():
        monkeypatch.setattr(registration, name, value)
    monkeypatch.setattr(lineage_engine, "LOG", research / "lineage.jsonl")
    return candidate, memory, research


def test_registers_candidate_only_after_all_pre_oos_checks(queued_candidate):
    candidate, _, research = queued_candidate

    assert registration.register() == 0

    records = lineage_engine.read_lineage()
    assert len(records) == 1
    record = records[0]
    assert record["experiment_id"] == f"BC477:REGISTRATION:{candidate['candidate_hash']}"
    assert record["verdict"] == "REGISTERED"
    assert record["decision"] == "REGISTERED_CANDIDATE"
    assert record["result"]["status"] == "REGISTERED_NOT_EVALUATED"
    assert record["result"]["candidate_hash"] == candidate["candidate_hash"]
    assert record["result"]["family"] == "vwap_volume_profile"
    assert record["result"]["oos_selection_used"] is False
    assert not (research / "bc477_validation_result.json").exists()
    assert not (research / "oos/BC477_oos_result.json").exists()


def test_rejects_novelty_key_already_in_prior_registry(queued_candidate):
    _, memory, _ = queued_candidate
    memory["candidates"]["vwap_volume_profile||||above"] = {"bc": 12}
    write(registration.SEARCH_MEMORY, memory)

    with pytest.raises(registration.RegistrationBlocked, match="candidate_novelty_already_registered"):
        registration.validate_queued_candidate()


def test_rejects_selected_family_binding_mismatch(queued_candidate):
    _, memory, _ = queued_candidate
    memory["last_selected_family"] = "fvg_imbalance"
    write(registration.SEARCH_MEMORY, memory)

    with pytest.raises(registration.RegistrationBlocked, match="selected_family_record_mismatch"):
        registration.validate_queued_candidate()


def test_rejects_parent_failure_hash_mismatch(queued_candidate):
    _, _, research = queued_candidate
    write(research / "failure_analysis/BC476.json", {
        "bc": 476, "decision": "REJECT", "candidate_hash": "wrong-parent-hash",
    })

    with pytest.raises(registration.RegistrationBlocked, match="parent_failure_candidate_hash_mismatch"):
        registration.validate_queued_candidate()


def test_rejects_evaluation_without_registration_lineage(queued_candidate):
    _, _, research = queued_candidate
    write(research / "bc477_validation_result.json", {"bc": 477})

    with pytest.raises(registration.RegistrationBlocked, match="queued_candidate_has_evaluation_artifacts"):
        registration.validate_queued_candidate()


def test_existing_registration_is_idempotent_and_hash_bound(queued_candidate):
    candidate, _, _ = queued_candidate
    assert registration.register() == 0
    assert registration.register() == 0
    records = lineage_engine.read_lineage()
    assert len(records) == 1
    assert records[0]["result"]["candidate_hash"] == candidate["candidate_hash"]


def test_queue_candidate_hash_mismatch_fails_closed(queued_candidate):
    _, _, research = queued_candidate
    queue = json.loads((research / "bc_queue.json").read_text(encoding="utf-8"))
    queue[0]["candidate_hash"] = "different-hash"
    write(research / "bc_queue.json", queue)

    with pytest.raises(registration.RegistrationBlocked, match="queue_candidate_hash_mismatch"):
        registration.validate_queued_candidate()


def test_preflight_only_validates_without_appending_registration_lineage(queued_candidate):
    _, _, research = queued_candidate

    assert registration.register(preflight_only=True) == 0
    assert not (research / "lineage.jsonl").exists()



def test_rejects_constant_self_comparison_before_registration(queued_candidate):
    candidate, _, research = queued_candidate
    candidate["hypothesis_id"] = "discovered_primitive"
    candidate["conceptual_change"] = "Test a mean-reversion ratio predicate."
    candidate["discovery_spec"] = {
        "mechanism_family": "mean_reversion",
        "operator": "ratio",
        "left": "close",
        "right": "close",
        "direction": "above",
        "threshold": 1.0,
    }
    candidate["novelty_key"] = "mean_reversion|ratio|close|close|above"
    candidate["novelty_type"] = "structural_mechanism"
    candidate["parameterization"] = {"window": None, "threshold": 1.0}
    candidate["candidate_hash"] = canonical_hash(candidate)
    write(research / "autonomous_candidates/BC477.json", candidate)
    queue = json.loads((research / "bc_queue.json").read_text(encoding="utf-8"))
    for key in ("candidate_hash", "discovery_spec", "novelty_key", "hypothesis_id", "evidence_sources"):
        queue[0][key] = candidate[key]
    write(research / "bc_queue.json", queue)

    with pytest.raises(
        registration.RegistrationBlocked,
        match="candidate_semantic_validation_failed:self_comparison_is_constant",
    ):
        registration.validate_queued_candidate()


def test_rejects_novelty_already_registered_under_a_different_hash(queued_candidate):
    candidate, _, research = queued_candidate
    prior = {
        "experiment_id": "BC477:REGISTRATION:older-hash",
        "verdict": "REGISTERED",
        "result": {
            "candidate_hash": "older-hash",
            "novelty_key": candidate["novelty_key"],
            "family": "vwap_volume_profile",
        },
    }
    write(research / "lineage.jsonl", json.dumps(prior) + "\\n")

    with pytest.raises(
        registration.RegistrationBlocked,
        match="candidate_novelty_already_registered_in_lineage",
    ):
        registration.validate_queued_candidate()
