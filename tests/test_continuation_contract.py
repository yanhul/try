from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (ROOT / ".github/workflows/bc-research-controller.yml").read_text()
CONTINUATION = (ROOT / ".github/workflows/bc-research-continuation.yml").read_text()
WATCHDOG = (ROOT / ".github/workflows/bc-research-watchdog.yml").read_text()
CAMPAIGN = (ROOT / "research/campaign_controller.py").read_text()
REGISTRATION = (ROOT / "research/register_candidate_lineage.py").read_text()


def test_controller_authorization_is_emitted_only_after_durable_push():
    assert "CONTROLLER_CONTINUE_REQUEST" in CAMPAIGN
    assert "CONTROLLER_CONTINUE_AUTHORIZED" not in CAMPAIGN
    assert "CONTROLLER_CONTINUE_AUTHORIZED kind=PROGRESS reason=DURABLE_QUEUE" in CONTROLLER
    assert CONTROLLER.index('echo "STATE_PERSISTED"') < CONTROLLER.index("CONTROLLER_CONTINUE_AUTHORIZED")
    assert "STATE_PERSISTENCE_CONFLICT" in CONTROLLER
    assert "CONTINUATION_INTENT_PERSISTENCE_CONFLICT" in CONTROLLER


def test_candidate_registration_is_committed_before_evaluation():
    preflight = CONTROLLER.index("Validate and register queued candidate lineage before evaluation")
    campaign = CONTROLLER.index("Run bounded autonomous research campaign")
    postflight = CONTROLLER.index("Register queued candidate lineage after controller queue creation")
    persist = CONTROLLER.index("Persist autonomous research state")
    assert preflight < campaign < postflight < persist
    assert "steps.queued_registration_preflight.outputs.created != 'true'" in CONTROLLER
    assert "research.register_candidate_lineage --validate-only" in CONTROLLER
    assert "CANDIDATE_REGISTRATION_LINEAGE_CREATED" in REGISTRATION
    assert "parent_failure_hash" in REGISTRATION
    assert "candidate_novelty_already_registered" in REGISTRATION


def test_completed_success_receipt_is_reconciled_not_left_active():
    assert "CONTINUATION_RECEIPT_COMPLETED_SUCCESS" in CONTINUATION
    assert 'source_run_id="$dispatch_id"' in CONTINUATION
    assert 'status="STALE"' in CONTINUATION
    assert "CONTINUATION_STALE_INTENT_RECONCILED_FROM_DURABLE_QUEUE" in CONTINUATION
    assert "CONTINUATION_CONTROLLER_FAILED" in CONTINUATION


def test_dispatch_run_id_is_canonical_with_legacy_url_fallback():
    assert "'.dispatch_run_id // empty'" in CONTINUATION
    assert "'.dispatch_run_url // empty'" in CONTINUATION
    assert ".dispatch_run_id=($id|tonumber)" in CONTINUATION
    assert ".dispatch_head_sha=$sha" in CONTINUATION
    assert "CONTINUATION_DISPATCH_AMBIGUOUS" in CONTINUATION
    assert "CONTINUATION_DISPATCH_NO_RECEIPT" in CONTINUATION
    assert "run_workflow_id" in CONTINUATION
    assert "run_repo" in CONTINUATION
    assert "run_branch" in CONTINUATION
    assert "run_event" in CONTINUATION
    assert "run_sha" in CONTINUATION


def test_watchdog_invokes_reconciler_not_controller():
    assert "gh workflow run bc-research-continuation.yml --repo \"$GITHUB_REPOSITORY\" --ref main" in WATCHDOG
    assert "gh workflow run bc-research-controller.yml" not in WATCHDOG
    assert "CONTINUATION_RECEIPT_COMPLETED_SUCCESS" in WATCHDOG
    assert "CONTROLLER_ACTIVE count=$active; no duplicate dispatch." in WATCHDOG


def test_watchdog_requires_queue_candidate_parent_failure_and_current_checkpoint():
    assert "DURABLE_QUEUE_CHECKPOINT_MISMATCH" in WATCHDOG
    assert "DURABLE_QUEUE_CANDIDATE_OR_PARENT_FAILURE_INVALID" in WATCHDOG
    assert "research.register_candidate_lineage --preflight-only" in WATCHDOG
    assert "state_current" in WATCHDOG and "state_next" in WATCHDOG
    assert "DURABLE_WORK_REQUIRES_RECONCILIATION" in WATCHDOG


def test_controller_continuation_and_watchdog_share_one_concurrency_lane():
    assert "group: try-bc-research-continuation-main" in CONTROLLER
    assert "group: try-bc-research-continuation-main" in CONTINUATION
    assert "group: try-bc-research-continuation-main" in WATCHDOG


def test_controller_does_not_trigger_from_state_pushes_or_delete_receipts():
    assert "  push:" not in CONTROLLER
    assert "rm -f research/continuation_intent.json" not in CONTROLLER
