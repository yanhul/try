from research.autonomous_repair import terminal_status


def test_provider_quota_hold_is_not_reported_as_repair_failure():
    assert terminal_status([{"attempt": 1, "status": "HOLD", "reason": "provider_quota_exhausted"}]) == "HOLD"


def test_reconciliation_blocked_outcome_takes_precedence_over_hold():
    assert terminal_status([
        {"attempt": 1, "status": "HOLD", "reason": "provider_quota_exhausted"},
        {"attempt": 2, "status": "BLOCKED", "reason": "reconciliation_required"},
    ]) == "BLOCKED"


def test_only_failed_verification_results_remain_fail():
    assert terminal_status([{"attempt": 1, "status": "FAIL"}]) == "FAIL"
    assert terminal_status([]) == "FAIL"
