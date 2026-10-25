from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (ROOT / '.github/workflows/bc-research-controller.yml').read_text()
CONTINUATION = (ROOT / '.github/workflows/bc-research-continuation.yml').read_text()
WATCHDOG = (ROOT / '.github/workflows/bc-research-watchdog.yml').read_text()
REGISTRATION = (ROOT / 'research/candidate_registration.py').read_text()


def test_controller_emits_only_a_request_before_persistence():
    assert 'CONTROLLER_CONTINUE_REQUESTED kind=' in (ROOT / 'research/campaign_controller.py').read_text()
    assert 'CONTROLLER_CONTINUE_AUTHORIZED kind=' not in (ROOT / 'research/campaign_controller.py').read_text()
    assert 'CONTINUATION_REQUEST_RECORDED kind=$kind' in CONTROLLER
    assert 'continue_kind=$kind' in CONTROLLER
    assert 'CONTROLLER_CONTINUE_AUTHORIZED kind=$CONTINUE_KIND' in CONTROLLER


def test_controller_authorization_occurs_after_successful_main_push():
    assert 'id: persist_state' in CONTROLLER
    assert 'steps.persist_state.outputs.persisted == \'true\'' in CONTROLLER
    push = CONTROLLER.rfind('git push origin HEAD:main')
    authorization = CONTROLLER.index('CONTROLLER_CONTINUE_AUTHORIZED kind=$CONTINUE_KIND')
    assert push < authorization
    assert 'CONTINUATION_AUTHORIZATION_MAIN_PERSISTENCE_UNPROVEN' in CONTROLLER
    assert 'research.candidate_registration authorize' in CONTROLLER
    assert 'Path(\'research/continuation_intent.json\').write_text' not in CONTROLLER


def test_completed_success_receipt_is_not_treated_as_active():
    assert "'.dispatch_run_id // empty'" in CONTINUATION
    assert "'.dispatch_run_url // empty'" in CONTINUATION
    assert 'CONTINUATION_RECEIPT_COMPLETED dispatch_run_id=' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_ACTIVE dispatch_run_id=' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_INVALID dispatch_run_id=' in CONTINUATION
    assert 'run_status\" != \"completed\"' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_CONFIRMED_SUCCESS' not in CONTINUATION


def test_completed_receipt_recovery_requires_current_durable_registration():
    assert 'research.candidate_registration status' in CONTINUATION
    assert 'REGISTRATION_REQUIRED' in CONTINUATION
    assert 'CONTINUATION_REGISTRATION_ONLY_DISPATCHED=true' in CONTINUATION
    assert 'python -m research.candidate_registration authorize --source-run-id' in CONTINUATION
    assert 'CONTROLLER_CONTINUE_AUTHORIZED kind=$kind source_run_id=$source_for_pending after_persist=true' in CONTINUATION


def test_dispatch_run_id_is_canonical_and_bound_to_github_run_identity():
    assert "'.dispatch_run_id // empty'" in CONTINUATION
    assert "'.dispatch_run_url // empty'" in CONTINUATION
    assert '.dispatch_run_id=($id|tonumber)' in CONTINUATION
    assert '.dispatch_head_sha=$sha' in CONTINUATION
    assert 'CONTINUATION_DISPATCH_AMBIGUOUS' in CONTINUATION
    assert 'CONTINUATION_DISPATCH_NO_RECEIPT' in CONTINUATION
    assert 'run_workflow_id' in CONTINUATION and 'run_repo' in CONTINUATION
    assert 'run_branch' in CONTINUATION and 'run_sha' in CONTINUATION
    assert 'run_event' in CONTINUATION
    assert 'dispatched_run' in CONTINUATION


def test_watchdog_reconciles_completed_success_and_fails_closed_without_run_id():
    assert 'DURABLE_QUEUE_CHECKPOINT_MISMATCH; reconcile only from current main artifacts.' in WATCHDOG
    assert 'CONTINUATION_RECEIPT_COMPLETED_SUCCESS' in WATCHDOG
    assert 'CONTINUATION_RECEIPT_ACTIVE id=$dispatch_id' in WATCHDOG
    assert 'CONTINUATION_RECEIPT_INVALID_MISSING_RUN_ID; fail closed.' in WATCHDOG
    assert 'research.candidate_registration status' in WATCHDOG
    assert 'BC_CONTROLLER_REGISTRATION_ONLY_DISPATCHED=true' in WATCHDOG
    assert 'BC_CONTINUATION_RECONCILER_DISPATCHED=true' in WATCHDOG
    assert 'CONTINUATION_RECEIPT_ACTIVE_OR_SUCCESS' not in WATCHDOG


def test_durable_queue_authorization_checks_candidate_failure_novelty_family_and_lineage():
    assert 'DURABLE_QUEUE_PARENT_FAILURE_INVALID' in REGISTRATION
    assert 'DURABLE_QUEUE_SELECTED_FAMILY_MISMATCH' in REGISTRATION
    assert 'DURABLE_QUEUE_SELECTED_SURVIVOR_MISMATCH' in REGISTRATION
    assert 'DURABLE_QUEUE_NOVELTY_REPLAY' in REGISTRATION
    assert 'DURABLE_QUEUE_REGISTRATION_LINEAGE_MISSING' in REGISTRATION
    assert 'DURABLE_QUEUE_EVALUATION_PRECEDED_REGISTRATION' in REGISTRATION


def test_durable_queue_and_checkpoint_must_match_before_pending_intent():
    assert 'validate_queued_candidate(root, require_registration=True)' in REGISTRATION
    assert 'CONTINUATION_AUTHORIZATION_MAIN_PERSISTENCE_UNPROVEN' in REGISTRATION
    assert '"status": "PENDING"' in REGISTRATION
    assert '"checkpoint_seq": bundle["checkpoint_seq"]' in REGISTRATION
    assert '"candidate_hash": bundle["candidate_hash"]' in REGISTRATION


def test_controller_does_not_trigger_from_state_pushes_or_delete_receipts():
    assert "  push:" not in CONTROLLER
    assert 'github.event_name !=' not in CONTROLLER
    assert 'rm -f research/continuation_intent.json' not in CONTROLLER


def test_continuation_dispatch_receipt_persistence_is_conflict_aware():
    assert 'CONTINUATION_RECEIPT_SUPERSEDED' in CONTINUATION
    assert 'git fetch origin main' in CONTINUATION
    assert 'git rebase origin/main' in CONTINUATION
    assert 'CONTINUATION_RECEIPT_PERSISTED' in CONTINUATION
