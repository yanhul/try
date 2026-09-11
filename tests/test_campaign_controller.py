from research.campaign_controller import continuation_allowed


def test_old_screened_count_cannot_resume_without_new_progress():
    assert continuation_allowed(
        before_screened=30,
        screened=30,
        phase="ACT",
        last_error=None,
        terminal_state=False,
    ) is False


def test_provider_hold_cannot_resume_even_if_screened_increases():
    assert continuation_allowed(
        before_screened=30,
        screened=31,
        phase="WAIT_RETRY",
        last_error="HOLD_PROVIDER_ROUTER",
        terminal_state=False,
    ) is False


def test_hold_cannot_resume_with_stale_progress():
    assert continuation_allowed(
        before_screened=30,
        screened=30,
        phase="HOLD",
        last_error="HOLD_PROVIDER_ROUTER",
        terminal_state=False,
    ) is False


def test_fresh_nonterminal_progress_can_continue():
    assert continuation_allowed(
        before_screened=30,
        screened=31,
        phase="PERSISTED",
        last_error=None,
        terminal_state=False,
    ) is True


def test_terminal_state_cannot_continue():
    assert continuation_allowed(
        before_screened=30,
        screened=31,
        phase="PERSISTED",
        last_error=None,
        terminal_state=True,
    ) is False
