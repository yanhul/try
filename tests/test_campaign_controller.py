from pathlib import Path
import json
import sys

from research import campaign_controller
from research.campaign_controller import controller_command, continuation_allowed, qualifying_bcs, reconcile_campaign_state
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
        "history": [
            *({"bc": bc, "decision": "REJECT"} for bc in range(31, 167)),
        ],
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


def test_epoch_seed_requires_explicit_controller_handoff(monkeypatch, tmp_path):
    monkeypatch.delenv("RESEARCH_EPOCH_SEED_FAILURE", raising=False)
    assert epoch_seed_failure(166, 167) is None

    seed = tmp_path / ".epoch_seed_failure.json"
    seed.write_text(json.dumps({
        "kind": "epoch_seed_failure",
        "decision": "SEED_EPOCH",
        "parent_bc": 166,
        "epoch_start_bc": 167,
        "research_evidence": False,
        "repair_context": True,
    }), encoding="utf-8")
    monkeypatch.setenv("RESEARCH_EPOCH_SEED_FAILURE", str(seed))
    assert epoch_seed_failure(166, 167) is None


def test_epoch_seed_contract_is_consumed_only_from_controller_path(monkeypatch):
    from research import bc_controller
    seed = bc_controller.ROOT / "research" / ".epoch_seed_failure.json"
    seed.write_text(json.dumps({
        "kind": "epoch_seed_failure",
        "decision": "SEED_EPOCH",
        "parent_bc": 166,
        "epoch_start_bc": 167,
        "research_evidence": False,
        "repair_context": True,
    }), encoding="utf-8")
    monkeypatch.setenv("RESEARCH_EPOCH_SEED_FAILURE", str(seed))
    try:
        assert epoch_seed_failure(166, 167) == seed.resolve()
        assert epoch_seed_failure(165, 167) is None
    finally:
        seed.unlink(missing_ok=True)


def test_controller_is_invoked_as_package_module():
    assert controller_command() == [sys.executable, "-m", "research.bc_controller"]

# Astra trigger: force a fresh controller run after authority-boundary fixes.
