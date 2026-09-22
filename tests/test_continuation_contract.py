from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (ROOT / '.github/workflows/bc-research-controller.yml').read_text()
CONTINUATION = (ROOT / '.github/workflows/bc-research-continuation.yml').read_text()


def test_controller_persists_intent_before_dispatch_lane():
    assert 'research/continuation_intent.json' in CONTROLLER
    assert 'created_by_run_id' in CONTROLLER
    assert 'gh workflow run bc-research-controller.yml' not in CONTROLLER
    assert 'sleep 60' not in CONTROLLER
    assert "cron: '*/15 * * * *'" not in CONTROLLER
    assert 'STATE_PERSISTENCE_REBASED_ON_LATEST_MAIN' in CONTROLLER
    assert 'durable paths changed on remote' in CONTROLLER


def test_continuation_is_event_driven_and_durable():
    assert 'workflow_run:' in CONTINUATION
    assert 'BC Research Controller' in CONTINUATION
    assert 'types:' in CONTINUATION and 'completed' in CONTINUATION
    assert 'status' in CONTINUATION and 'DISPATCHED' in CONTINUATION
    assert 'gh workflow run bc-research-controller.yml --ref main' in CONTINUATION
    assert 'CREATED_BY_RUN_ID' in CONTINUATION
    assert 'source_run_id' in CONTINUATION
    assert 'CONTINUATION_DISPATCH_NO_RECEIPT' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_PERSISTED' in CONTINUATION
    assert 'sleep' not in CONTINUATION.lower()


def test_controller_has_fast_dispatch_with_durable_receipt():
    assert 'Fast event-driven continuation dispatch' in CONTROLLER
    assert 'CONTINUATION_DISPATCH_NO_RECEIPT' in CONTROLLER
    assert "intent['status']='DISPATCHED'" in CONTROLLER
    assert 'CONTINUATION_RECEIPT_PERSISTED' in CONTROLLER


def test_continuation_ignores_completed_controller_runs():
    assert '.status == "queued"' in CONTINUATION
    assert '.status == "in_progress"' in CONTINUATION
    assert '.status == "pending"' in CONTINUATION
    assert '.status == "waiting"' in CONTINUATION


def test_watchdog_serializes_with_continuation_lane():
    watchdog = (ROOT / '.github/workflows/bc-research-watchdog.yml').read_text()
    assert 'group: try-bc-research-continuation-main' in watchdog
    assert 'CONTINUATION_RECEIPT_PRESENT' in watchdog


def test_controller_does_not_trigger_from_state_pushes():
    assert "  push:" not in CONTROLLER
    assert 'github.event_name !=' not in CONTROLLER


def test_controller_does_not_delete_or_own_dispatch_receipts():
    assert 'rm -f research/continuation_intent.json' not in CONTROLLER
    assert 'research/continuation_intent.json)' not in CONTROLLER


def test_failed_dispatch_receipt_is_reopened():
    assert 'gh run view "$dispatch_id"' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_STALE' in CONTINUATION
    assert 'i["status"]="PENDING"' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_CONFIRMED_SUCCESS' in CONTINUATION
