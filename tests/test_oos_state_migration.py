import copy

from research.bc_controller import append_promotion_event, migrate_legacy_state
from research.oos_lifecycle import OOSLifecycleError


def test_legacy_promotion_verdict_is_demoted_to_unknown():
    state = {
        "history": [
            {
                "bc": 306,
                "candidate_hash": "candidate-306",
                "decision": "PROMOTE_TO_FUTURE_OOS_TEST",
                "oos_verdict": "OOS_FAIL",
            }
        ],
        "terminal": False,
        "terminal_reason": "OOS_FAIL",
    }
    changed = migrate_legacy_state(state)
    assert changed is True
    entry = state["history"][0]
    assert entry["decision"] == "LEGACY_UNVERIFIED_OOS"
    assert entry["legacy_oos_verdict"] == "OOS_FAIL"
    assert entry["oos_verdict"] is None
    assert entry["oos_executed"] is False
    assert entry["oos_state"] == "UNKNOWN"
    assert state["terminal_reason"] is None
    assert state["legacy_terminal_reason"] == "OOS_FAIL"
    assert state["state_schema_version"] == 2
    assert state["state_migrations"][0]["migration_id"] == "OOS_CANONICAL_V1"


def test_legacy_migration_is_idempotent():
    state = {
        "history": [
            {
                "bc": 306,
                "decision": "PROMOTE_TO_FUTURE_OOS_TEST",
                "oos_verdict": "OOS_FAIL",
            }
        ],
        "terminal": False,
        "terminal_reason": "OOS_FAIL",
    }
    migrate_legacy_state(state)
    snapshot = copy.deepcopy(state)
    assert migrate_legacy_state(state) is False
    assert state == snapshot


def test_malformed_history_fails_closed():
    state = {"history": [{"bc": 1}, "not-an-entry"]}
    try:
        migrate_legacy_state(state)
    except OOSLifecycleError as exc:
        assert str(exc) == "STATE_HISTORY_ENTRY_INVALID"
    else:
        raise AssertionError("malformed durable history was accepted")


def test_promotion_event_is_persisted_without_verdict():
    state = {"history": []}
    assert append_promotion_event(state, 310, "candidate-310") is True
    event = state["history"][-1]
    assert event["decision"] == "PROMOTE_TO_FUTURE_OOS_TEST"
    assert event["oos_verdict"] is None
    assert event["oos_executed"] is False
    assert event["oos_state"] == "OOS_PENDING"


def test_promotion_event_is_not_duplicated_on_resume():
    state = {"history": []}
    assert append_promotion_event(state, 310, "candidate-310") is True
    assert append_promotion_event(state, 310, "candidate-310") is False
    assert len(state["history"]) == 1
