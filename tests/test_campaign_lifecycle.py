from research.campaign_lifecycle import LifecycleAction, LifecycleInput, decide


def test_durable_queue_wins_over_screening_progress():
    x = LifecycleInput(False, True, False, True, False, False, False)
    assert decide(x) is LifecycleAction.CONTINUE_DURABLE_QUEUE


def test_budget_exhaustion_is_terminal_accounting_path():
    x = LifecycleInput(False, True, True, False, False, False, False)
    assert decide(x) is LifecycleAction.BUDGET_EXHAUSTED


def test_retry_is_explicit_liveness_event():
    x = LifecycleInput(False, True, False, False, True, False, False)
    assert decide(x) is LifecycleAction.CONTINUE_RETRY


def test_progress_event_does_not_depend_on_screened_counter():
    x = LifecycleInput(False, True, False, False, False, False, True)
    assert decide(x) is LifecycleAction.CONTINUE_PROGRESS


def test_no_durable_work_or_progress_holds():
    x = LifecycleInput(False, True, False, False, False, False, False)
    assert decide(x) is LifecycleAction.HOLD


def test_invalid_terminal_is_blocked():
    x = LifecycleInput(True, False, False, False, False, False, False)
    assert decide(x) is LifecycleAction.BLOCKED


def test_blocked_state_has_priority():
    x = LifecycleInput(True, True, False, True, True, True, True)
    assert decide(x) is LifecycleAction.BLOCKED
