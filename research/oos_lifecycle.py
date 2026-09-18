"""Canonical OOS lifecycle and verdict gate.

OOS performance verdicts are evaluation facts, not dispatch/transport facts.
A verdict is legal only after execution and a bound execution receipt exist.
Provider failures and missing evidence remain UNKNOWN/BLOCKED and can never
be converted into OOS_PASS/OOS_FAIL by recovery code.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class OOSLifecycleError(ValueError):
    pass


class OOSState(StrEnum):
    VALIDATION_PASS = "VALIDATION_PASS"
    OOS_AUTHORIZED = "OOS_AUTHORIZED"
    OOS_DISPATCHED = "OOS_DISPATCHED"
    OOS_EXECUTED = "OOS_EXECUTED"
    OOS_RECEIPT = "OOS_RECEIPT"
    OOS_EVALUATED = "OOS_EVALUATED"
    OOS_PENDING = "OOS_PENDING"
    OOS_PASS = "OOS_PASS"
    OOS_FAIL = "OOS_FAIL"
    PROVIDER_FAIL = "PROVIDER_FAIL"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"

_TRANSITIONS: dict[OOSState, frozenset[OOSState]] = {
    OOSState.VALIDATION_PASS: frozenset({OOSState.OOS_AUTHORIZED}),
    OOSState.OOS_AUTHORIZED: frozenset({OOSState.OOS_DISPATCHED, OOSState.BLOCKED}),
    OOSState.OOS_DISPATCHED: frozenset({OOSState.OOS_EXECUTED, OOSState.PROVIDER_FAIL, OOSState.UNKNOWN}),
    OOSState.OOS_EXECUTED: frozenset({OOSState.OOS_RECEIPT, OOSState.UNKNOWN}),
    OOSState.OOS_RECEIPT: frozenset({OOSState.OOS_EVALUATED, OOSState.UNKNOWN}),
    OOSState.OOS_EVALUATED: frozenset({OOSState.OOS_PASS, OOSState.OOS_FAIL}),
    OOSState.PROVIDER_FAIL: frozenset({OOSState.UNKNOWN, OOSState.OOS_DISPATCHED, OOSState.BLOCKED}),
    OOSState.UNKNOWN: frozenset({OOSState.OOS_AUTHORIZED, OOSState.BLOCKED}),
    OOSState.BLOCKED: frozenset(),
    OOSState.OOS_PASS: frozenset(),
    OOSState.OOS_FAIL: frozenset(),
    OOSState.OOS_PENDING: frozenset({OOSState.OOS_AUTHORIZED, OOSState.BLOCKED}),
}


def advance(current: OOSState | str, target: OOSState | str) -> OOSState:
    current = OOSState(current)
    target = OOSState(target)
    if target not in _TRANSITIONS[current]:
        raise OOSLifecycleError(f"ILLEGAL_OOS_TRANSITION:{current}->{target}")
    return target


def promotion_event() -> dict[str, Any]:
    """Create the only legal pre-OOS promotion marker."""
    return {
        "decision": "PROMOTE_TO_FUTURE_OOS_TEST",
        "oos_state": OOSState.OOS_PENDING.value,
        "oos_verdict": None,
        "oos_executed": False,
    }


def provider_failure_event(reason: str) -> dict[str, Any]:
    """Provider/transport failure is never an OOS performance verdict."""
    return {
        "oos_state": OOSState.PROVIDER_FAIL.value,
        "oos_verdict": None,
        "oos_executed": False,
        "provider_failure_reason": str(reason),
    }


def _require_receipt_binding(result: dict[str, Any], receipt: dict[str, Any]) -> None:
    if result.get("oos_executed") is not True:
        raise OOSLifecycleError("OOS_VERDICT_REQUIRES_EXECUTION")
    if not receipt:
        raise OOSLifecycleError("OOS_VERDICT_REQUIRES_RECEIPT")
    for key in ("bc", "candidate_hash", "dataset_sha256", "protocol_sha256"):
        if key == "dataset_sha256":
            expected = result.get("dataset", {}).get("sha256")
        else:
            expected = result.get(key)
        if receipt.get(key) != expected:
            raise OOSLifecycleError(f"OOS_RECEIPT_BINDING_MISMATCH:{key}")
    if receipt.get("receipt_type") != "OOS_EXECUTION_RECEIPT":
        raise OOSLifecycleError("OOS_RECEIPT_TYPE")
    if receipt.get("schema_version") != 1:
        raise OOSLifecycleError("OOS_RECEIPT_SCHEMA")
    if receipt.get("oos_executed") is not True:
        raise OOSLifecycleError("OOS_RECEIPT_REQUIRES_EXECUTION")
    if receipt.get("oos_selection_used") is not False:
        raise OOSLifecycleError("OOS_RECEIPT_SELECTION_CONTAMINATION")
    if receipt.get("metrics") != result.get("metrics"):
        raise OOSLifecycleError("OOS_RECEIPT_METRICS_MISMATCH")


def evaluate_oos(result: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    """Canonical evaluation gate: execution + receipt first, verdict second."""
    _require_receipt_binding(result, receipt)
    passed = result.get("oos_passed")
    if not isinstance(passed, bool):
        raise OOSLifecycleError("OOS_EVALUATION_VERDICT_MISSING")
    verdict = OOSState.OOS_PASS.value if passed else OOSState.OOS_FAIL.value
    return {
        "oos_state": OOSState.OOS_EVALUATED.value,
        "oos_verdict": verdict,
        "oos_executed": True,
        "receipt_type": receipt["receipt_type"],
        "receipt_schema_version": receipt["schema_version"],
        "bc": result["bc"],
        "candidate_hash": result["candidate_hash"],
    }


def terminal_reason_from_oos(result: dict[str, Any], receipt: dict[str, Any]) -> str:
    """Only an evaluated OOS result may become a terminal reason."""
    evaluation = evaluate_oos(result, receipt)
    return evaluation["oos_verdict"]


def assert_history_entry_legal(entry: dict[str, Any]) -> None:
    """Adversarial boundary for durable history."""
    decision = entry.get("decision")
    verdict = entry.get("oos_verdict")
    executed = entry.get("oos_executed")
    if decision == "PROMOTE_TO_FUTURE_OOS_TEST":
        if verdict is not None:
            raise OOSLifecycleError("PROMOTION_MUST_NOT_CARRY_OOS_VERDICT")
        if executed is not False:
            raise OOSLifecycleError("PROMOTION_MUST_BE_PRE_OOS")
    if verdict is not None:
        if verdict not in {OOSState.OOS_PASS.value, OOSState.OOS_FAIL.value}:
            raise OOSLifecycleError("UNKNOWN_OOS_VERDICT")
        if executed is not True:
            raise OOSLifecycleError("OOS_VERDICT_REQUIRES_EXECUTION")
