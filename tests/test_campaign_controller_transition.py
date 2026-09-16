from research.campaign_controller import LifecycleAction, lifecycle_transition


def test_durable_queue_is_authoritative_liveness_signal():
    assert lifecycle_transition(
        terminal_state=False, terminal_outcome_valid=True, budget_exhausted=False,
        durable_queue=True, retry_allowed=False, blocked=False, progress_event=False,
    ) is LifecycleAction.CONTINUE_DURABLE_QUEUE


def test_screened_counter_is_accounting_not_liveness():
    assert lifecycle_transition(
        terminal_state=False, terminal_outcome_valid=True, budget_exhausted=False,
        durable_queue=False, retry_allowed=False, blocked=False, progress_event=True,
    ) is LifecycleAction.CONTINUE_PROGRESS


def test_zero_screened_progress_holds_when_no_work_exists():
    assert lifecycle_transition(
        terminal_state=False, terminal_outcome_valid=True, budget_exhausted=False,
        durable_queue=False, retry_allowed=False, blocked=False, progress_event=False,
    ) is LifecycleAction.HOLD


def test_retry_is_explicit_transition():
    assert lifecycle_transition(
        terminal_state=False, terminal_outcome_valid=True, budget_exhausted=False,
        durable_queue=False, retry_allowed=True, blocked=False, progress_event=False,
    ) is LifecycleAction.CONTINUE_RETRY


def test_budget_is_checked_after_durable_work():
    assert lifecycle_transition(
        terminal_state=False, terminal_outcome_valid=True, budget_exhausted=True,
        durable_queue=True, retry_allowed=False, blocked=False, progress_event=False,
    ) is LifecycleAction.CONTINUE_DURABLE_QUEUE


def test_terminal_requires_valid_outcome():
    assert lifecycle_transition(
        terminal_state=True, terminal_outcome_valid=True, budget_exhausted=False,
        durable_queue=False, retry_allowed=False, blocked=False, progress_event=True,
    ) is LifecycleAction.TERMINAL
    assert lifecycle_transition(
        terminal_state=True, terminal_outcome_valid=False, budget_exhausted=False,
        durable_queue=False, retry_allowed=False, blocked=False, progress_event=True,
    ) is LifecycleAction.BLOCKED


def test_blocked_has_fail_closed_priority():
    assert lifecycle_transition(
        terminal_state=False, terminal_outcome_valid=True, budget_exhausted=False,
        durable_queue=True, retry_allowed=True, blocked=True, progress_event=True,
    ) is LifecycleAction.BLOCKED
