from pathlib import Path
import json
import sys

from research import campaign_controller
from research.campaign_controller import controller_command, continuation_allowed, qualifying_bcs, screened_bcs, reconcile_campaign_state
from research.bc_controller import epoch_seed_failure


def test_old_screened_count_cannot_resume_without_new_progress():
    assert continuation_allowed(new_screened=0, phase="ACT", last_error=None, terminal_state=False) is False


def test_provider_hold_cannot_resume_even_if_new_progress_exists():
    assert continuation_allowed(new_screened=1, phase="WAIT_RETRY", last_error="HOLD_PROVIDER_ROUTER", terminal_state=False) is False


def test_hold_cannot_resume_with_stale_progress():
    assert continuation_allowed(new_screened=0, phase="HOLD", last_error="HOLD_PROVIDER_ROUTER", terminal_state=False) is False


def test_fresh_nonterminal_progress_can_continue():
    assert continuation_allowed(new_screened=1, phase="PERSISTED", last_error=None, terminal_state=False) is True


def test_terminal_state_cannot_continue():
    assert continuation_allowed(new_screened=1, phase="PERSISTED", last_error=None, terminal_state=True) is False


def test_screened_bcs_is_distinct_from_qualifying_bcs():
    history = [
        {"bc": 1, "decision": "REJECT"},
        {"bc": 2, "decision": "PROMOTE_TO_FUTURE_OOS_TEST"},
        {"bc": 3, "event_type": "OOS_EVALUATION", "oos_verdict": "OOS_FAIL"},
        {"bc": 4, "decision": "HOLD"},
    ]
    assert screened_bcs(history) == {1, 2, 3}
    assert qualifying_bcs(history) == {1, 2}


def test_qualifying_bcs_counts_only_screening_decisions():
    history = [
        {"bc": 1, "decision": "REJECT"},
        {"bc": 2, "decision": "PROMOTE_TO_FUTURE_OOS_TEST"},
        {"bc": 3, "decision": "HOLD"},
        {"bc": "not-a-bc", "decision": "REJECT"},
    ]
    assert qualifying_bcs(history) == {1, 2}


def test_new_campaign_epoch_ignores_prior_history_for_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", tmp_path / "failures")
    state = {
        "campaign_id": "BTCUSDT-1H-AUTONOMOUS-002",
        "campaign_epoch_initialized": True,
        "campaign_start_bc": 167,
        "current_bc": 166,
        "history": [*({"bc": bc, "decision": "REJECT"} for bc in range(31, 167))],
    }
    _, start, screened = reconcile_campaign_state(state, 100)
    assert start == 167
    assert screened == 0
    assert state["campaign_screened"] == 0


def test_new_campaign_epoch_counts_only_post_boundary_history(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", tmp_path / "failures")
    state = {
        "campaign_id": "BTCUSDT-1H-AUTONOMOUS-002",
        "campaign_epoch_initialized": True,
        "campaign_start_bc": 167,
        "history": [
            {"bc": 166, "decision": "REJECT"},
            {"bc": 167, "decision": "REJECT"},
            {"bc": 168, "decision": "PROMOTE_TO_FUTURE_OOS_TEST"},
        ],
    }
    _, start, screened = reconcile_campaign_state(state, 100)
    assert start == 167
    assert screened == 2
    assert state["campaign_screened"] == 2


def test_missing_capability_is_repaired_to_declared_research(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "STATE", tmp_path / "state.json")
    state = {"campaign_id": "BTCUSDT-1H-AUTONOMOUS-002"}
    policy = {"campaign_id": "BTCUSDT-1H-AUTONOMOUS-002"}
    campaign_controller._ensure_research_capability(state, policy)
    assert state["capabilities"] == ["research"]
    assert state["capability_repaired_from_campaign_policy"] is True
    persisted = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert persisted["capabilities"] == ["research"]


def test_existing_capability_is_not_overwritten(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "STATE", tmp_path / "state.json")
    state = {"campaign_id": "BTCUSDT-1H-AUTONOMOUS-002", "capabilities": ["research"]}
    campaign_controller._ensure_research_capability(state, {"campaign_id": "BTCUSDT-1H-AUTONOMOUS-002"})
    assert state["capabilities"] == ["research"]
    assert not (tmp_path / "state.json").exists()


def test_epoch_seed_requires_explicit_controller_handoff(monkeypatch, tmp_path):
    monkeypatch.delenv("RESEARCH_EPOCH_SEED_FAILURE", raising=False)
    assert epoch_seed_failure(166, 167) is None
    seed = tmp_path / ".epoch_seed_failure.json"
    seed.write_text(json.dumps({"kind": "epoch_seed_failure", "decision": "SEED_EPOCH", "parent_bc": 166, "epoch_start_bc": 167, "research_evidence": False, "repair_context": True}), encoding="utf-8")
    monkeypatch.setenv("RESEARCH_EPOCH_SEED_FAILURE", str(seed))
    assert epoch_seed_failure(166, 167) is None


def test_epoch_seed_contract_is_consumed_only_from_controller_path(monkeypatch):
    from research import bc_controller
    seed = bc_controller.ROOT / "research" / ".epoch_seed_failure.json"
    seed.write_text(json.dumps({"kind": "epoch_seed_failure", "decision": "SEED_EPOCH", "parent_bc": 166, "epoch_start_bc": 167, "research_evidence": False, "repair_context": True}), encoding="utf-8")
    monkeypatch.setenv("RESEARCH_EPOCH_SEED_FAILURE", str(seed))
    try:
        assert epoch_seed_failure(166, 167) == seed.resolve()
        assert epoch_seed_failure(165, 167) is None
    finally:
        seed.unlink(missing_ok=True)


def test_controller_is_invoked_as_package_module():
    assert controller_command() == [sys.executable, "-m", "research.bc_controller"]


def test_historical_oos_failure_requires_durable_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(campaign_controller, "OOS_DIR", tmp_path / "oos")
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", tmp_path / "failures")
    state = {"campaign_terminal": True, "campaign_terminal_reason": "OOS_FAIL", "campaign_outcome": "NO_EDGE_FOUND", "terminal": True, "current_bc": 202, "next_bc": 203, "phase": "TERMINAL"}
    assert campaign_controller._migrate_candidate_oos_terminal(state) is False
    assert state["campaign_terminal"] is True


def test_historical_oos_failure_is_migrated_from_durable_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(campaign_controller, "OOS_DIR", tmp_path / "oos")
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", tmp_path / "failures")
    for directory in (campaign_controller.CANDIDATE_DIR, campaign_controller.OOS_DIR): directory.mkdir(parents=True)
    candidate_hash = "candidate-202-hash"
    (campaign_controller.CANDIDATE_DIR / "BC202.json").write_text(json.dumps({"bc": 202, "parent_bc": 201, "hypothesis_id": "H202", "candidate_hash": candidate_hash, "conceptual_change": "test change", "evidence_sources": ["durable-test"]}), encoding="utf-8")
    (campaign_controller.OOS_DIR / "BC202_oos_result.json").write_text(json.dumps({"bc": 202, "candidate_hash": candidate_hash, "oos_executed": True, "oos_selection_used": False, "oos_passed": False, "metrics": {"profit_factor": 0.8}, "dataset": {"sha256": "dataset-sha"}, "protocol_sha256": "protocol-sha"}), encoding="utf-8")
    (campaign_controller.OOS_DIR / "BC202_oos_result_receipt.json").write_text(json.dumps({"receipt_type": "OOS_EXECUTION_RECEIPT", "schema_version": 1, "bc": 202, "candidate_hash": candidate_hash, "oos_executed": True, "oos_selection_used": False, "oos_passed": False, "metrics": {"profit_factor": 0.8}, "dataset_sha256": "dataset-sha", "protocol_sha256": "protocol-sha"}), encoding="utf-8")
    state = {"campaign_terminal": True, "campaign_terminal_reason": "OOS_FAIL", "campaign_outcome": "NO_EDGE_FOUND", "terminal": True, "current_bc": 202, "next_bc": 203, "phase": "TERMINAL", "oos_failed_bc": 202}
    assert campaign_controller._migrate_candidate_oos_terminal(state) is True
    assert state["campaign_terminal"] is False
    assert state["terminal"] is False
    assert state["next_bc"] == 203
    assert state["campaign_terminal_reason"] is None
    assert state["last_oos_migration"] == {"failed_bc": 202, "reason": "OOS_FAIL", "action": "CANDIDATE_REJECTION"}
    failure = json.loads((campaign_controller.FAILURE_DIR / "BC202.json").read_text(encoding="utf-8"))
    assert failure["decision"] == "REJECT"
    assert failure["oos_verdict"] == "OOS_FAIL"
    assert failure["candidate_hash"] == candidate_hash


def test_epoch_boundary_resets_budget_without_erasing_history(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", tmp_path / "failures")
    state = {"campaign_id": "BTCUSDT-1H-AUTONOMOUS-002", "campaign_epoch": 1,
             "campaign_epoch_initialized": True, "campaign_start_bc": 167,
             "next_bc": 267, "campaign_terminal": False, "history":
             [{"bc": bc, "decision": "REJECT"} for bc in range(167, 267)]}
    _, start, screened = reconcile_campaign_state(state, 100)
    assert start == 167 and screened == 100
    next_bc = int(state["next_bc"])
    state.update(campaign_epoch=2, campaign_start_bc=next_bc, campaign_screened=0)
    assert state["campaign_epoch"] == 2
    assert state["campaign_start_bc"] == 267
    assert state["campaign_screened"] == 0
    assert len(state["history"]) == 100


def test_epoch_rollover_fails_closed_on_unresolved_candidate(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", tmp_path / "failures")
    monkeypatch.setattr(campaign_controller, "OOS_DIR", tmp_path / "oos")
    (tmp_path / "candidates").mkdir(parents=True)
    (tmp_path / "candidates" / "BC267.json").write_text(json.dumps({"bc": 267}), encoding="utf-8")
    state = {"campaign_terminal": False, "phase": "PERSISTED", "next_bc": 267, "retry_count": 0}
    assert campaign_controller.epoch_rollover_allowed(state, 167, 100, 100) is False


def test_epoch_rollover_fails_closed_on_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", tmp_path / "failures")
    monkeypatch.setattr(campaign_controller, "OOS_DIR", tmp_path / "oos")
    state = {"campaign_terminal": False, "phase": "WAIT_RETRY", "last_error": "provider_rate_limited", "next_bc": 267, "retry_count": 1}
    assert campaign_controller.epoch_rollover_allowed(state, 167, 100, 100) is False


def test_epoch_rollover_requires_exact_frontier(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", tmp_path / "failures")
    monkeypatch.setattr(campaign_controller, "OOS_DIR", tmp_path / "oos")
    state = {"campaign_terminal": False, "phase": "PERSISTED", "next_bc": 268, "retry_count": 0}
    assert campaign_controller.epoch_rollover_allowed(state, 167, 100, 100) is False


def test_reconcile_recovers_multiple_epochs_from_durable_frontier(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", tmp_path / "failures")
    campaign_controller.CANDIDATE_DIR.mkdir(parents=True)
    campaign_controller.FAILURE_DIR.mkdir(parents=True)
    for bc in range(167, 459):
        (campaign_controller.CANDIDATE_DIR / f"BC{bc}.json").write_text(json.dumps({"bc": bc}), encoding="utf-8")
        (campaign_controller.FAILURE_DIR / f"BC{bc}.json").write_text(json.dumps({"bc": bc, "decision": "REJECT"}), encoding="utf-8")
    state = {
        "campaign_id": "BTCUSDT-1H-AUTONOMOUS-002",
        "campaign_epoch_initialized": True,
        "campaign_epoch": 1,
        "campaign_start_bc": 167,
        "next_bc": 459,
        "campaign_screened": 100,
        "history": [{"bc": bc, "decision": "REJECT"} for bc in range(167, 459)],
    }
    _, start, screened = reconcile_campaign_state(state, 100)
    assert start == 367
    assert screened == 92
    assert state["campaign_epoch"] == 3
    assert state["campaign_start_bc"] == 367
    assert state["campaign_screened"] == 92
    assert state["next_bc"] == 459


def test_reconcile_rolls_exact_completed_epoch_to_next_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", tmp_path / "candidates")
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", tmp_path / "failures")
    campaign_controller.CANDIDATE_DIR.mkdir(parents=True)
    campaign_controller.FAILURE_DIR.mkdir(parents=True)
    for bc in range(167, 267):
        (campaign_controller.CANDIDATE_DIR / f"BC{bc}.json").write_text(json.dumps({"bc": bc}), encoding="utf-8")
        (campaign_controller.FAILURE_DIR / f"BC{bc}.json").write_text(json.dumps({"bc": bc, "decision": "REJECT"}), encoding="utf-8")
    state = {
        "campaign_epoch_initialized": True,
        "campaign_epoch": 1,
        "campaign_start_bc": 167,
        "next_bc": 267,
        "history": [{"bc": bc, "decision": "REJECT"} for bc in range(167, 267)],
    }
    _, start, screened = reconcile_campaign_state(state, 100)
    assert start == 267
    assert screened == 0
    assert state["campaign_epoch"] == 2
    assert state["next_bc"] == 267
