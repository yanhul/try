from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (ROOT / '.github/workflows/bc-research-controller.yml').read_text()
CONTINUATION = (ROOT / '.github/workflows/bc-research-continuation.yml').read_text()
WATCHDOG = (ROOT / '.github/workflows/bc-research-watchdog.yml').read_text()


def test_controller_persists_authorized_intent_before_dispatch_lane():
    assert 'research/continuation_intent.json' in CONTROLLER
    assert 'created_by_run_id' in CONTROLLER
    assert 'gh workflow run bc-research-controller.yml' not in CONTROLLER
    assert 'STATE_PERSISTENCE_REBASED_ON_LATEST_MAIN' in CONTROLLER
    assert 'STATE_PERSISTENCE_CONFLICT' in CONTROLLER
    assert "if [ \"$CONTINUE\" = \"true\" ]" in CONTROLLER
    assert "'status': 'PENDING'" in CONTROLLER


def test_continuation_validates_exact_successful_source_run():
    assert 'workflow_run:' in CONTINUATION
    assert 'BC Research Controller' in CONTINUATION
    assert 'types:' in CONTINUATION and 'completed' in CONTINUATION
    assert "'.conclusion' <<<\"$source_run\"" in CONTINUATION
    assert 'test "$(jq -r \'.conclusion\' <<<"$source_run")" = "success"' in CONTINUATION
    assert 'event_source_run_id="$(jq -r \'.workflow_run.id // 0\'' in CONTINUATION
    assert 'test "$event_source_run_id" = "$source_run_id"' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_CONFIRMED_SUCCESS' in CONTINUATION


def test_completed_success_receipt_is_terminal_and_not_redispatched():
    assert 'run_status="$(jq -r \'.status // ""\' <<<"$run_state")"' in CONTINUATION
    assert 'run_conclusion="$(jq -r \'.conclusion // ""\' <<<"$run_state")"' in CONTINUATION
    assert 'elif [ "$run_conclusion" = "success" ]; then' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_CONFIRMED_SUCCESS' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_STALE' in CONTINUATION


def test_dispatch_run_id_is_persisted_and_legacy_url_is_reconciled():
    assert "'.dispatch_run_id // empty'" in CONTINUATION
    assert "'.dispatch_run_url // empty'" in CONTINUATION
    assert '.dispatch_run_id=($id|tonumber)' in CONTINUATION
    assert '.dispatch_head_sha=$sha' in CONTINUATION
    assert 'CONTINUATION_DISPATCH_AMBIGUOUS' in CONTINUATION
    assert 'CONTINUATION_DISPATCH_NO_RECEIPT' in CONTINUATION
    assert 'gh workflow run bc-research-controller.yml --repo "$GITHUB_REPOSITORY" --ref main' in CONTINUATION
    assert 'gh run list --repo "$GITHUB_REPOSITORY" --workflow "$controller_workflow_id"' in CONTINUATION


def test_dispatch_receipt_is_bound_to_expected_workflow_repo_and_branch():
    assert 'run_workflow_id="$(jq -r \'.workflow_id // 0\' <<<"$run_state")"' in CONTINUATION
    assert 'run_repo="$(jq -r \'.repository.full_name // ""\' <<<"$run_state")"' in CONTINUATION
    assert 'run_branch="$(jq -r \'.head_branch // ""\' <<<"$run_state")"' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_INVALID' in CONTINUATION
    assert 'run_sha="$(jq -r \'.head_sha // ""\' <<<"$run_state")"' in CONTINUATION
    assert 'expected_sha="$(jq -r \'.dispatch_head_sha // empty\' <<<"$intent")"' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_INVALID' in CONTINUATION


def test_watchdog_requires_durable_queue_authorization_and_successful_source():
    assert 'group: try-bc-research-continuation-main' in WATCHDOG
    assert 'CONTINUATION_RECEIPT_PRESENT' in WATCHDOG
    assert 'DURABLE_QUEUE_UNAUTHORIZED' in WATCHDOG
    assert 'DURABLE_QUEUE_SOURCE_INVALID' in WATCHDOG
    assert 'DURABLE_QUEUE_CHECKPOINT_MISMATCH' in WATCHDOG
    assert 'state_checkpoint' in WATCHDOG and 'intent_checkpoint' in WATCHDOG
    assert "(.status == \"PENDING\" or .status == \"DISPATCHED\" or .status == \"STALE\")" in WATCHDOG
    assert 'dispatch_run_id // empty' in WATCHDOG
    assert 'gh workflow run bc-research-continuation.yml --repo "$GITHUB_REPOSITORY" --ref main' in WATCHDOG
    assert 'gh workflow run bc-research-controller.yml' not in WATCHDOG


def test_watchdog_does_not_duplicate_active_or_successful_dispatch():
    assert 'CONTINUATION_RECEIPT_ACTIVE_OR_SUCCESS' in WATCHDOG
    assert 'CONTROLLER_ACTIVE count=$active; no duplicate dispatch.' in WATCHDOG
    assert 'CONTINUATION_RECEIPT_INVALID' in WATCHDOG
    assert 'run_sha="$(jq -r \'.head_sha // ""\' <<<"$run_state")"' in WATCHDOG
    assert 'expected_sha="$(jq -r \'.dispatch_head_sha // empty\' <<<"$intent")"' in WATCHDOG


def test_controller_does_not_trigger_from_state_pushes_or_delete_receipts():
    assert "  push:" not in CONTROLLER
    assert 'github.event_name !=' not in CONTROLLER
    assert 'rm -f research/continuation_intent.json' not in CONTROLLER


def test_continuation_dispatch_receipt_persistence_is_conflict_aware():
    assert 'CONTINUATION_RECEIPT_SUPERSEDED' in CONTINUATION
    assert 'git fetch origin main' in CONTINUATION
    assert 'git rebase origin/main' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_PERSISTED' in CONTINUATION
