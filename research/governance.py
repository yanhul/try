"""Fail-closed execution governance primitives.

This module is intentionally small: lifecycle code asks for a permit; executors
must require that permit. A denied/invalid predecessor can never become an
execution request by accident.
"""
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class GovernanceDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass(frozen=True)
class Permit:
    decision: GovernanceDecision
    action: str
    effect_id: str
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.decision is GovernanceDecision.ALLOW


def authorize(
    *,
    action: str,
    effect_id: str,
    predecessor_valid: bool,
    evidence_valid: bool,
    authority_valid: bool,
    lineage_valid: bool,
    blocked: bool = False,
) -> Permit:
    """Return a permit only when every execution precondition is valid."""
    checks = (
        ("BLOCKED", not blocked),
        ("INVALID_PREDECESSOR", predecessor_valid),
        ("INVALID_EVIDENCE", evidence_valid),
        ("INVALID_AUTHORITY", authority_valid),
        ("INVALID_LINEAGE", lineage_valid),
    )
    for reason, ok in checks:
        if not ok:
            return Permit(GovernanceDecision.DENY, action, effect_id, reason)
    return Permit(GovernanceDecision.ALLOW, action, effect_id)


def require_permit(permit: Permit) -> None:
    """Hard execution boundary: callers cannot continue after denial."""
    if not permit.allowed:
        raise PermissionError(
            f"execution denied: action={permit.action} effect_id={permit.effect_id} "
            f"reason={permit.reason}"
        )


def validate_state_invariants(state: Mapping[str, Any]) -> tuple[str, ...]:
    """Return invariant violations; callers should fail closed before persist/execute."""
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
