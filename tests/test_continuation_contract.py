from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (ROOT / '.github/workflows/bc-research-controller.yml').read_text()
CONTINUATION = (ROOT / '.github/workflows/bc-research-continuation.yml').read_text()
WATCHDOG = (ROOT / '.github/workflows/bc-research-watchdog.yml').read_text()


def test_controller_persists_intent_before_dispatch_lane():
    assert 'research/continuation_intent.json' in CONTROLLER
    assert 'created_by_run_id' in CONTROLLER
    assert 'gh workflow run bc-research-controller.yml' not in CONTROLLER
    assert 'sleep 60' not in CONTROLLER
    assert "cron: '*/15 * * * *'" not in CONTROLLER
    assert 'STATE_PERSISTENCE_REBASED_ON_LATEST_MAIN' in CONTROLLER
    assert 'STATE_PERSISTENCE_CONFLICT' in CONTROLLER


def test_continuation_is_event_driven_and_durable():
    assert 'workflow_run:' in CONTINUATION
    assert 'BC Research Controller' in CONTINUATION
    assert 'types:' in CONTINUATION and 'completed' in CONTINUATION
    assert 'status' in CONTINUATION and 'DISPATCHED' in CONTINUATION
    assert 'gh workflow run bc-research-controller.yml --ref main' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_PERSISTED' in CONTINUATION
    assert 'sleep' in CONTINUATION.lower()


def test_controller_has_fast_dispatch_with_durable_receipt():
    assert 'Fast event-driven continuation dispatch' in CONTROLLER
    assert 'CONTINUATION_DISPATCH_NO_RECEIPT' in CONTINUATION
    assert 'PENDING' in CONTROLLER
    assert 'CONTINUATION_RECEIPT_PERSISTED' in CONTINUATION


def test_completed_success_receipt_does_not_deadlock_authorized_queue():
    assert 'CONTINUATION_RECEIPT_COMPLETED_SUCCESS' in CONTINUATION
    assert 'CONTINUATION_BLOCKED_NO_DURABLE_QUEUE_AUTHORIZATION' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_ACTIVE' in CONTINUATION


def test_dispatch_run_id_is_canonical_with_legacy_url_fallback():
    assert "'.dispatch_run_id // empty'" in CONTINUATION
    assert "'.dispatch_run_id // empty'" in WATCHDOG
    assert 'dispatch_run_url' in CONTINUATION and 'dispatch_run_url' in WATCHDOG
    assert 'CONTINUATION_RECEIPT_INVALID_MISSING_RUN_ID' in WATCHDOG


def test_durable_queue_authorization_is_required():
    assert 'research/bc_queue.json' in CONTINUATION
    assert 'research/bc_queue.json' in WATCHDOG
    assert 'CONTINUATION_BLOCKED_NO_DURABLE_QUEUE_AUTHORIZATION' in CONTINUATION
    assert 'WATCHDOG_BLOCKED_NO_DURABLE_QUEUE_AUTHORIZATION' in WATCHDOG


def test_watchdog_serializes_with_continuation_lane():
    assert 'group: try-bc-research-continuation-main' in WATCHDOG
    assert 'CONTINUATION_RECEIPT_PRESENT' in WATCHDOG


def test_controller_does_not_trigger_from_state_pushes():
    assert "  push:" not in CONTROLLER
    assert 'github.event_name !=' not in CONTROLLER


def test_controller_does_not_delete_or_own_dispatch_receipts():
    assert 'rm -f research/continuation_intent.json' not in CONTROLLER


def test_failed_dispatch_receipt_is_reopened():
    assert 'CONTINUATION_RECEIPT_COMPLETED' in WATCHDOG
    assert 'CONTINUATION_RECEIPT_INVALID_MISSING_RUN_ID' in WATCHDOG


def test_receipt_lookup_ignores_failed_runs():
    assert 'run_status' in CONTINUATION
    assert 'run_conclusion' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_STALE' in CONTINUATION
    assert 'CONTROLLER_ACTIVE count=' in WATCHDOG
