"""TRY worker execution path for AIOS-authorized external effects.

Order of operations for one handoff (``run_once``):

1. ``claim()`` from SQLite — a *scheduling snapshot only*, never authority.
2. ``authoritative_dispatch()`` — reload the AIOS effect-of-record, contract and
   permit via AIOS public APIs; require exact binding and state == DISPATCHED.
3. ``heartbeat()`` — the lease must still be owned by this worker.
4. ``core.runtime.execute_attempt`` — the AIOS boundary calls the provider and
   persists the observation (or UNKNOWN) in AIOS.
5. ``mirror_verified_terminal()`` — mirror only an AIOS-verified receipt; on any
   doubt the row becomes / stays UNKNOWN. Nothing is ever requeued.

The enqueue/retry helpers create and dispatch AIOS effects through AIOS public
APIs *without* calling the provider, so execution happens only in the worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import engine.aios_path  # noqa: F401  (pins AIOS as `core`)
from core.authority import authorize, load_contract, load_permit
from core.durable_runtime import validate_submission
from core.effect_authority import create_effect, dispatch, retry_dispatch
from core.runtime import execute_attempt

from engine.aios_authority_reader import (
    AuthorityRejected, TERMINAL, authoritative_dispatch, load_effect_of_record,
    pin_authority_root,
)
from engine.aios_durable_runtime import DurableQueueError, TrySQLiteDurableRuntime


@dataclass(frozen=True)
class WorkerResult:
    effect_id: str
    attempt_id: str
    execution_attempted: bool
    queue_status: str
    reason: str


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _check_contract(aios_dir, contract_id, permit_id, actor, provider):
    authorize(aios_dir, contract_id, permit_id)
    contract = load_contract(aios_dir, contract_id)
    permit = load_permit(aios_dir, permit_id)
    if permit["actor"] != actor or contract["actor"] != actor:
        raise PermissionError("actor does not match authorized contract")
    if not any(isinstance(r, str) and r.split("@", 1)[0] == provider
               for r in contract.get("capabilities", [])):
        raise PermissionError("provider capability is not authorized by contract")
    if "external_effect" not in contract.get("allowed_effects", []):
        raise PermissionError("external effect is not authorized by contract")
    return contract


def enqueue_dispatched(aios_dir, contract_id, permit_id, logical_operation_id, actor,
                       runtime: TrySQLiteDurableRuntime):
    """AIOS create+dispatch attempt 1, then hand off to TRY. Provider is NOT called."""
    aios_dir = pin_authority_root(aios_dir)
    _text(logical_operation_id, "logical_operation_id")
    provider = runtime.provider_name
    _check_contract(aios_dir, contract_id, permit_id, actor, provider)
    effect = create_effect(aios_dir, contract_id, logical_operation_id, actor, permit_id,
                           "external_effect")
    if effect["state"] != "PLANNED":
        raise RuntimeError("logical operation already has a non-planned effect")
    attempt_id = f"{effect['effect_id']}:attempt:1"
    effect = dispatch(aios_dir, effect["effect_id"], actor, attempt_id, provider)
    submission = runtime.submit(effect=effect, attempt_id=attempt_id)
    validate_submission(effect, submission, attempt_id, provider)
    return effect


def enqueue_retry(aios_dir, contract_id, permit_id, effect_id, actor, attempt,
                  runtime: TrySQLiteDurableRuntime):
    """Explicit, AIOS-authorized bounded retry of an UNKNOWN effect. Provider NOT called.

    The scheduler gate is checked *before* AIOS ``retry_dispatch`` so a gated
    retry does not consume an AIOS attempt; ``runtime.retry`` re-checks it
    atomically after dispatch.
    """
    aios_dir = pin_authority_root(aios_dir)
    provider = runtime.provider_name
    _check_contract(aios_dir, contract_id, permit_id, actor, provider)
    current = load_effect_of_record(aios_dir, effect_id)
    if current.get("contract_id") != contract_id or current.get("permit_id") != permit_id:
        raise PermissionError("effect contract/permit binding mismatch")
    if current.get("state") != "UNKNOWN":
        raise RuntimeError(f"retry requires AIOS UNKNOWN, got {current.get('state')}")
    if not runtime.can_retry(effect_id=effect_id, attempt=attempt):
        raise DurableQueueError("retry gated by scheduler state")
    attempt_id = f"{effect_id}:attempt:{attempt}"
    dispatched = retry_dispatch(aios_dir, effect_id, actor, attempt_id, provider, attempt)
    submission = runtime.retry(effect=dispatched, attempt_id=attempt_id, attempt=attempt)
    validate_submission(dispatched, submission, attempt_id, provider)
    return dispatched


class AiosDurableWorker:
    def __init__(self, *, aios_dir, runtime: TrySQLiteDurableRuntime, adapter, actor: str,
                 worker_id: str):
        self.aios_dir = pin_authority_root(aios_dir)
        self.runtime = runtime
        self.adapter = adapter
        self.actor = _text(actor, "actor")
        self.worker_id = _text(worker_id, "worker_id")
        provider = _text(getattr(adapter, "name", None), "adapter.name")
        if provider != runtime.provider_name:
            raise ValueError("adapter provider does not match runtime provider")
        self.provider = provider

    def _unknown(self, claim, reason, execution_attempted):
        self.runtime.mark_unknown(effect_id=claim["effect_id"], attempt_id=claim["attempt_id"],
                                  worker_id=self.worker_id, reason=reason)
        row = self.runtime.get_handoff(effect_id=claim["effect_id"], attempt_id=claim["attempt_id"])
        return WorkerResult(claim["effect_id"], claim["attempt_id"], execution_attempted,
                            row["status"] if row else "MISSING", reason)

    def _mirror_or_unknown(self, claim, execution_attempted, prefix):
        try:
            verified = self.runtime.mirror_verified_terminal(
                aios_dir=self.aios_dir, effect_id=claim["effect_id"],
                attempt_id=claim["attempt_id"], worker_id=self.worker_id)
            return WorkerResult(claim["effect_id"], claim["attempt_id"], execution_attempted,
                                verified["state"], f"{prefix}: mirrored verified AIOS receipt")
        except (AuthorityRejected, DurableQueueError) as exc:
            return self._unknown(claim, f"{prefix}: {exc}", execution_attempted)

    def run_once(self) -> WorkerResult | None:
        claim = self.runtime.claim(worker_id=self.worker_id)
        if claim is None:
            return None
        snapshot = claim["effect"]
        try:
            if claim["provider"] != self.provider or snapshot.get("provider") != self.provider:
                raise AuthorityRejected("claimed handoff provider does not match worker provider")
            if snapshot.get("actor") != self.actor:
                raise AuthorityRejected("claimed handoff actor does not match worker actor")
            expected = {k: snapshot.get(k) for k in ("effect_id", "attempt_id", "attempt",
                                                     "contract_id", "permit_id", "effect_type")}
            if expected["effect_id"] != claim["effect_id"] or expected["attempt_id"] != claim["attempt_id"]:
                raise AuthorityRejected("claimed row identity differs from its payload")
            contract, effect = authoritative_dispatch(
                self.aios_dir, expected=expected, actor=self.actor, provider=self.provider)
        except AuthorityRejected as exc:
            # Not executable. If AIOS already holds a verified terminal receipt
            # for this exact attempt (e.g. in-process execute()), mirror it;
            # otherwise fail closed to UNKNOWN.
            return self._mirror_or_unknown(claim, False, f"pre-execution authority rejected: {exc}")

        try:
            self.runtime.heartbeat(effect_id=claim["effect_id"], attempt_id=claim["attempt_id"],
                                   worker_id=self.worker_id)
        except DurableQueueError as exc:
            # Lease lost: do not execute. Row is left for recover_expired_leases -> UNKNOWN.
            row = self.runtime.get_handoff(effect_id=claim["effect_id"], attempt_id=claim["attempt_id"])
            return WorkerResult(claim["effect_id"], claim["attempt_id"], False,
                                row["status"] if row else "MISSING", f"lease lost: {exc}")

        try:
            execute_attempt(self.aios_dir, contract, effect, self.actor, self.adapter,
                            claim["attempt_id"])
        except Exception as exc:
            # The provider may or may not have acted (e.g. AIOS observe persistence
            # failed after the provider returned). Ambiguous => UNKNOWN.
            return self._unknown(claim, f"AIOS execution boundary raised: "
                                        f"{type(exc).__name__}: {exc}", True)

        # Never trust the return value: re-read the AIOS effect-of-record.
        try:
            state = load_effect_of_record(self.aios_dir, claim["effect_id"]).get("state")
        except AuthorityRejected as exc:
            return self._unknown(claim, f"post-execution authority unreadable: {exc}", True)
        if state in TERMINAL:
            return self._mirror_or_unknown(claim, True, "post-execution")
        return self._unknown(claim, f"AIOS recorded non-terminal state {state!r}", True)


__all__ = ["AiosDurableWorker", "WorkerResult", "enqueue_dispatched", "enqueue_retry"]
