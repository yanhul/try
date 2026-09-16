import pytest

from research.governance import (EffectRequest, EffectStage, GovernanceDecision,
                                  Receipt, assert_state_invariants, authorize,
                                  authorize_effect, require_permit,
                                  validate_state_invariants)


def test_effect_requires_all_provenance_and_idempotency():
    req = EffectRequest("e1", "CONTROLLER_EXECUTE", "p1", "ev1", "a1", "l1", "idem-1")
    permit = authorize_effect(req, predecessor_valid=True, evidence_valid=True,
                              authority_valid=True, lineage_valid=True)
    assert permit.decision is GovernanceDecision.ALLOW
    require_permit(permit)


@pytest.mark.parametrize("field", ["predecessor_valid", "evidence_valid", "authority_valid", "lineage_valid"])
def test_invalid_provenance_denies_execution(field):
    checks = dict(predecessor_valid=True, evidence_valid=True, authority_valid=True, lineage_valid=True)
    checks[field] = False
    permit = authorize(action="EXECUTE", effect_id="e1", idempotency_key="idem", **checks)
    assert not permit.allowed
    with pytest.raises(PermissionError):
        require_permit(permit)


def test_missing_idempotency_key_denies_execution():
    permit = authorize(action="EXECUTE", effect_id="e1", predecessor_valid=True,
                       evidence_valid=True, authority_valid=True, lineage_valid=True)
    assert permit.reason == "MISSING_IDEMPOTENCY_KEY"


def test_blocked_state_has_priority_over_other_inputs():
    permit = authorize(action="EXECUTE", effect_id="e1", predecessor_valid=True,
                       evidence_valid=True, authority_valid=True, lineage_valid=True,
                       blocked=True, idempotency_key="idem")
    assert permit.reason == "BLOCKED"
    with pytest.raises(PermissionError):
        require_permit(permit)


def test_receipt_identity_is_bound_to_effect_attempt_and_idempotency():
    receipt = Receipt("e1", "attempt-1", "idem-1", EffectStage.RECEIPT,
                      "OBSERVED", "ev1", "l1")
    assert (receipt.effect_id, receipt.attempt_id, receipt.idempotency_key) == ("e1", "attempt-1", "idem-1")


def test_nonterminal_state_cannot_carry_terminal_reason():
    state = {"campaign_terminal": False, "campaign_terminal_reason": "OOS_FAIL"}
    assert "NONTERMINAL_HAS_TERMINAL_REASON" in validate_state_invariants(state)
    with pytest.raises(ValueError):
        assert_state_invariants(state)


def test_valid_terminal_oos_state_requires_explicit_failed_bc():
    state = {"campaign_terminal": True, "campaign_terminal_reason": "OOS_FAIL", "oos_failed_bc": 247}
    assert_state_invariants(state)
