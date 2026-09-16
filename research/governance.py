"""Fail-closed governance primitives for the research execution boundary."""
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class GovernanceDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class EffectStage(StrEnum):
    EFFECT = "EFFECT"
    DISPATCH = "DISPATCH"
    EXECUTE_ATTEMPT = "EXECUTE_ATTEMPT"
    RECEIPT = "RECEIPT"


@dataclass(frozen=True)
class EffectRequest:
    effect_id: str
    action: str
    predecessor_ref: str
    evidence_ref: str
    authority_ref: str
    lineage_ref: str
    idempotency_key: str


@dataclass(frozen=True)
class Permit:
    decision: GovernanceDecision
    action: str
    effect_id: str
    idempotency_key: str
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.decision is GovernanceDecision.ALLOW


@dataclass(frozen=True)
class Receipt:
    effect_id: str
    attempt_id: str
    idempotency_key: str
    stage: EffectStage
    status: str
    evidence_ref: str
    lineage_ref: str


def authorize(*, action: str, effect_id: str, predecessor_valid: bool,
              evidence_valid: bool, authority_valid: bool, lineage_valid: bool,
              blocked: bool = False, idempotency_key: str = "") -> Permit:
    checks = (("BLOCKED", not blocked), ("INVALID_PREDECESSOR", predecessor_valid),
              ("INVALID_EVIDENCE", evidence_valid), ("INVALID_AUTHORITY", authority_valid),
              ("INVALID_LINEAGE", lineage_valid), ("MISSING_IDEMPOTENCY_KEY", bool(idempotency_key)))
    for reason, ok in checks:
        if not ok:
            return Permit(GovernanceDecision.DENY, action, effect_id, idempotency_key, reason)
    return Permit(GovernanceDecision.ALLOW, action, effect_id, idempotency_key)


def authorize_effect(request: EffectRequest, *, predecessor_valid: bool,
                     evidence_valid: bool, authority_valid: bool,
                     lineage_valid: bool, blocked: bool = False) -> Permit:
    return authorize(action=request.action, effect_id=request.effect_id,
                      predecessor_valid=predecessor_valid, evidence_valid=evidence_valid,
                      authority_valid=authority_valid, lineage_valid=lineage_valid,
                      blocked=blocked, idempotency_key=request.idempotency_key)


def require_permit(permit: Permit) -> None:
    if not permit.allowed:
        raise PermissionError(f"execution denied: action={permit.action} effect_id={permit.effect_id} reason={permit.reason}")


def validate_state_invariants(state: Mapping[str, Any]) -> tuple[str, ...]:
    violations: list[str] = []
    terminal = bool(state.get("campaign_terminal"))
    reason = state.get("campaign_terminal_reason")
    if not terminal and reason is not None:
        violations.append("NONTERMINAL_HAS_TERMINAL_REASON")
    if reason == "OOS_FAIL" and not isinstance(state.get("oos_failed_bc"), int):
        violations.append("OOS_FAIL_MISSING_FAILED_BC")
    return tuple(violations)


def assert_state_invariants(state: Mapping[str, Any]) -> None:
    violations = validate_state_invariants(state)
    if violations:
        raise ValueError("state invariant violation: " + ",".join(violations))
