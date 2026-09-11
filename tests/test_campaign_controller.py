from research.campaign_controller import continuation_allowed, qualifying_bcs


def test_old_screened_count_cannot_resume_without_new_progress():
    assert continuation_allowed(
        new_screened=0,
        phase="ACT",
        last_error=None,
        terminal_state=False,
    ) is False


def test_provider_hold_cannot_resume_even_if_new_progress_exists():
    assert continuation_allowed(
        new_screened=1,
        phase="WAIT_RETRY",
        last_error="HOLD_PROVIDER_ROUTER",
        terminal_state=False,
    ) is False


def test_hold_cannot_resume_with_stale_progress():
    assert continuation_allowed(
        new_screened=0,
        phase="HOLD",
        last_error="HOLD_PROVIDER_ROUTER",
        terminal_state=False,
    ) is False


def test_fresh_nonterminal_progress_can_continue():
    assert continuation_allowed(
        new_screened=1,
        phase="PERSISTED",
        last_error=None,
        terminal_state=False,
    ) is True


def test_terminal_state_cannot_continue():
    assert continuation_allowed(
        new_screened=1,
        phase="PERSISTED",
        last_error=None,
        terminal_state=True,
    ) is False


def test_qualifying_bcs_counts_only_screening_decisions():
    history = [
        {"bc": 1, "decision": "REJECT"},
        {"bc": 2, "decision": "PROMOTE_TO_FUTURE_OOS_TEST"},
        {"bc": 3, "decision": "HOLD"},
        {"bc": "not-a-bc", "decision": "REJECT"},
    ]
    assert qualifying_bcs(history) == {1, 2}
