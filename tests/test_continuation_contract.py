from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (ROOT / '.github/workflows/bc-research-controller.yml').read_text()
CONTINUATION = (ROOT / '.github/workflows/bc-research-continuation.yml').read_text()


def test_controller_persists_intent_before_dispatch_lane():
    assert 'research/continuation_intent.json' in CONTROLLER
    assert 'created_by_run_id' in CONTROLLER
    assert 'gh workflow run bc-research-controller.yml' not in CONTROLLER
    assert 'research/continuation_intent.json' in CONTROLLER
    assert 'sleep 60' not in CONTROLLER
    assert "cron: '*/15 * * * *'" not in CONTROLLER


def test_continuation_is_event_driven_and_durable():
    assert 'workflow_run:' in CONTINUATION
    assert 'BC Research Controller' in CONTINUATION
    assert 'types:' in CONTINUATION and 'completed' in CONTINUATION
    assert 'status' in CONTINUATION and 'DISPATCHED' in CONTINUATION
    assert 'gh workflow run bc-research-controller.yml --ref main' in CONTINUATION
    assert 'CONTINUATION_DISPATCH_NO_RECEIPT' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_PERSISTED' in CONTINUATION
    assert 'sleep' not in CONTINUATION.lower()
