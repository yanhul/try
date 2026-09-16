import pytest

from research.governance import (
    GovernanceDecision,
    assert_state_invariants,
    authorize,
    require_permit,
    validate_state_invariants,
)


def test_valid_execution_requires_all_authority_inputs():
    permit = authorize(
        action="CONTROLLER_EXECUTE",
        effect_id="effect-1",
        predecessor_valid=True,
        evidence_valid=True,
        authority_valid=True,
        lineage_valid=True,
    )
    assert permit.decision is GovernanceDecision.ALLOW
    require_permit(permit)


@pytest.mark.parametrize(
    "field",
    ["predecessor_valid", "evidence_valid", "authority_valid", "lineage_valid"],
)
def test_missing_execution_prerequisite_denies(field):
    checks = dict(
        predecessor_valid=True,
        evidence_valid=True,
        authority_valid=True,
        lineage_valid=True,
    )
    checks[field] = False
    permit = authorize(action="EXECUTE", effect_id="e1", **checks)
    assert not permit.allowed
    with pytest.raises(PermissionError):
        require_permit(permit)


def test_blocked_state_cannot_execute():
    permit = authorize(
        action="EXECUTE",
        effect_id="e2",
        predecessor_valid=True,
        evidence_valid=True,
        authority_valid=True,
        lineage_valid=True,
        blocked=True,
    )
    assert permit.reason == "BLOCKED"
    with pytest.raises(PermissionError):
        require_permit(permit)


def test_nonterminal_terminal_reason_is_invalid():
    state = {"campaign_terminal": False, "campaign_terminal_reason": "OOS_FAIL"}
    assert validate_state_invariants(state) == ("NONTERMINAL_HAS_TERMINAL_REASON", "OOS_FAIL_MISSING_FAILED_BC")
    with pytest.raises(ValueError):
        assert_state_invariants(state)


def test_oos_failure_requires_explicit_failed_bc():
    state = {"campaign_terminal": True, "campaign_terminal_reason": "OOS_FAIL"}
    assert "OOS_FAIL_MISSING_FAILED_BC" in validate_state_invariants(state)


def test_valid_nonterminal_state_has_no_terminal_reason():
    state = {"campaign_terminal": False, "campaign_terminal_reason": None}
    assert_state_invariants(state)
