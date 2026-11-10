"""Read-only, fail-closed view of the pinned AIOS authority store.

TRY never decides whether an effect may execute or whether it succeeded. This
module only *reads* AIOS records through AIOS public APIs and refuses to return
anything that does not bind exactly to the expected identity:

- ``authoritative_dispatch``: called by the worker immediately before provider
  execution. Returns the AIOS effect-of-record only if it is currently
  ``DISPATCHED`` for exactly the claimed effect/attempt/provider/actor/contract
  and its contract/permit still authorize it.
- ``verified_terminal``: called before TRY mirrors a terminal state. Returns the
  AIOS outcome only if AIOS durably recorded an observed terminal state with a
  digest-valid AIOS evidence record bound to the same effect/attempt/provider.

Every failure raises ``AuthorityRejected``; callers must treat that as
"not authorized / not proven" and fail closed.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from core.authority import authorize, load_contract, load_permit
from core.evidence import verify_evidence
from core.external_effect import load_effects
from core.mutation import recover_pending

TERMINAL = ("OBSERVED_SUCCESS", "OBSERVED_FAILURE")
_IDENTITY_FIELDS = ("effect_id", "attempt_id", "attempt", "provider", "actor",
                    "contract_id", "permit_id", "effect_type")


class AuthorityRejected(RuntimeError):
    """AIOS authority is missing, unreadable, stale or does not bind."""


def pin_authority_root(aios_dir: str | Path) -> str:
    """Resolve the AIOS state directory once; refuse missing/non-directories."""
    if not isinstance(aios_dir, (str, Path)) or not str(aios_dir).strip():
        raise ValueError("aios_dir must be a non-empty path")
    root = Path(aios_dir).expanduser().resolve()
    if not root.is_dir():
        raise AuthorityRejected(f"AIOS authority store is not a directory: {root}")
    return str(root)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthorityRejected(f"{name} must be a non-empty string")
    return value


def _provider_authorized(contract: Mapping[str, Any], provider: str) -> bool:
    return any(isinstance(ref, str) and ref.split("@", 1)[0] == provider
               for ref in contract.get("capabilities", []))


def load_effect_of_record(aios_dir: str, effect_id: str) -> dict:
    """Load one AIOS effect through public APIs; any read problem fails closed."""
    _text(effect_id, "effect_id")
    try:
        # Roll forward any half-committed AIOS batch first so we never read a
        # pre-commit snapshot of an effect AIOS has already journaled.
        recover_pending(aios_dir)
        effects = load_effects(aios_dir)
    except Exception as exc:  # unreadable/corrupt store, permissions, JSON errors
        raise AuthorityRejected(f"AIOS authority unreadable: {type(exc).__name__}: {exc}") from exc
    effect = effects.get(effect_id)
    if not isinstance(effect, dict):
        raise AuthorityRejected(f"AIOS has no effect-of-record for {effect_id}")
    if effect.get("record_type") != "EXTERNAL_EFFECT" or effect.get("effect_id") != effect_id:
        raise AuthorityRejected("AIOS effect record identity is malformed")
    return effect


def _bind_identity(effect: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    for field in _IDENTITY_FIELDS:
        if field not in expected:
            continue
        if effect.get(field) != expected[field]:
            raise AuthorityRejected(
                f"AIOS {field} binding mismatch: authority={effect.get(field)!r} "
                f"expected={expected[field]!r}"
            )
    attempt = effect.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise AuthorityRejected("AIOS effect attempt is invalid")
    if effect.get("attempt_id") != f"{effect['effect_id']}:attempt:{attempt}":
        raise AuthorityRejected("AIOS attempt_id is not bound to effect/attempt number")


def _authorized_contract(aios_dir: str, effect: Mapping[str, Any], actor: str,
                         provider: str) -> dict:
    try:
        contract_id = _text(effect.get("contract_id"), "effect.contract_id")
        permit_id = _text(effect.get("permit_id"), "effect.permit_id")
        authorize(aios_dir, contract_id, permit_id)
        contract = load_contract(aios_dir, contract_id)
        permit = load_permit(aios_dir, permit_id)
    except AuthorityRejected:
        raise
    except Exception as exc:
        raise AuthorityRejected(f"AIOS contract/permit rejected: {type(exc).__name__}: {exc}") from exc
    if contract.get("actor") != actor or permit.get("actor") != actor:
        raise AuthorityRejected("AIOS contract/permit actor does not match worker actor")
    if effect.get("policy_digest") != contract.get("policy_digest"):
        raise AuthorityRejected("AIOS effect policy digest differs from contract")
    if effect.get("max_attempts") != contract.get("max_attempts"):
        raise AuthorityRejected("AIOS effect attempt budget differs from contract")
    if effect["attempt"] > contract["max_attempts"]:
        raise AuthorityRejected("AIOS effect attempt exceeds contract budget")
    if not _provider_authorized(contract, provider):
        raise AuthorityRejected("provider capability is not authorized by AIOS contract")
    if effect.get("effect_type") not in contract.get("allowed_effects", []):
        raise AuthorityRejected("effect type is not authorized by AIOS contract")
    return contract


def authoritative_dispatch(aios_dir: str, *, expected: Mapping[str, Any], actor: str,
                           provider: str) -> tuple[dict, dict]:
    """Return (contract, effect) only if AIOS currently authorizes this exact attempt."""
    _text(actor, "actor")
    _text(provider, "provider")
    effect = load_effect_of_record(aios_dir, _text(expected.get("effect_id"), "expected.effect_id"))
    state = effect.get("state")
    if state != "DISPATCHED":
        raise AuthorityRejected(f"AIOS effect is not DISPATCHED (state={state!r})")
    _bind_identity(effect, {**expected, "provider": provider, "actor": actor})
    contract = _authorized_contract(aios_dir, effect, actor, provider)
    return contract, effect


def verified_terminal(aios_dir: str, *, effect_id: str, attempt_id: str,
                      provider: str, expected: Mapping[str, Any] | None = None) -> dict:
    """Return {'state', 'provider_operation_id', 'evidence_id', 'evidence_digest'} or raise.

    Only an AIOS-persisted observed terminal state with a digest-valid AIOS
    evidence record bound to this effect/attempt/provider is accepted.
    """
    effect = load_effect_of_record(aios_dir, effect_id)
    state = effect.get("state")
    if state not in TERMINAL:
        raise AuthorityRejected(f"AIOS has no observed terminal outcome (state={state!r})")
    _bind_identity(effect, {**(expected or {}), "effect_id": effect_id,
                            "attempt_id": attempt_id, "provider": provider})
    obs = effect.get("provider_observation")
    if not isinstance(obs, dict) or not obs:
        raise AuthorityRejected("AIOS terminal effect has no provider observation")
    if (obs.get("effect_id") != effect_id or obs.get("attempt_id") != attempt_id
            or obs.get("provider") != provider):
        raise AuthorityRejected("AIOS provider observation is not bound to effect/attempt/provider")
    op_id = obs.get("provider_operation_id")
    if not isinstance(op_id, str) or not op_id.strip():
        raise AuthorityRejected("AIOS provider observation lacks provider_operation_id")
    evidence = obs.get("evidence")
    if not isinstance(evidence, dict) or not verify_evidence(evidence):
        raise AuthorityRejected("AIOS evidence record is missing or fails digest verification")
    if evidence.get("provider") != provider:
        raise AuthorityRejected("AIOS evidence provider binding mismatch")
    if evidence.get("run_id") != attempt_id:
        raise AuthorityRejected("AIOS evidence run_id is not bound to this attempt")
    return {"state": state, "provider_operation_id": op_id,
            "evidence_id": evidence["evidence_id"], "evidence_digest": evidence["digest"]}


__all__ = ["AuthorityRejected", "TERMINAL", "pin_authority_root", "load_effect_of_record",
           "authoritative_dispatch", "verified_terminal"]
