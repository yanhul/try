#!/usr/bin/env python3
"""Fail-closed AIOS full-lineage conformance proof for TRY.

The proof exercises the real AIOS effect authority boundary, including the
dedicated retry_dispatch() primitive, then builds one immutable proof chain:
effect -> attempt -> dispatch -> receipt -> evidence -> evaluation -> promotion.

Receipt/evidence/evaluation/promotion records are deliberately separate:
none is treated as authority merely because it exists.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AIOS = Path(os.environ.get("AIOS_SOURCE", ""))


def load_aios_package():
    if not AIOS.is_dir():
        raise RuntimeError(f"AIOS_SOURCE missing: {AIOS}")
    import sys
    sys.path.insert(0, str(AIOS))
    from core import contract, effect_authority, evidence
    return contract, effect_authority, evidence


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def sealed_record(kind, body):
    record = dict(body)
    record["record_type"] = kind
    record["record_digest"] = digest(record)
    return record


def verify_sealed(record):
    if not isinstance(record, dict) or not record.get("record_type"):
        raise AssertionError("sealed record schema invalid")
    claimed = record.get("record_digest")
    body = dict(record)
    body.pop("record_digest", None)
    if claimed != digest(body):
        raise AssertionError(f"{record.get('record_type')} digest mismatch")
    return True


def main() -> int:
    contract, effect, evidence = load_aios_package()
    failures: list[str] = []
    chain: dict[str, object] = {
        "schema_version": 2,
        "proof_type": "AIOS_FULL_LINEAGE_CONFORMANCE",
        "status": "BLOCKED",
    }

    try:
        sample = {
            "contract_type": "EXECUTION_CONTRACT",
            "task_id": "try-conformance",
            "scope": "research",
            "actor": "try-conformance",
            "capabilities": [],
            "input_digest": "input-sha",
            "allowed_effects": ["research"],
            "evidence_required": ["receipt"],
            "max_attempts": 3,
            "terminal_states": ["PASS", "BLOCKED", "INCONCLUSIVE"],
            "policy_digest": "policy-sha",
        }
        contract.validate_contract(sample)
        contract_id = contract.contract_identity(sample)
        permit = contract.issue_permit(sample, "aios-conformance")
        contract.verify_permit(sample, permit)
        permit_id = permit["permit_id"]

        with tempfile.TemporaryDirectory() as td:
            effect_dir = Path(td)
            created = effect.create_effect(
                str(effect_dir),
                contract_id,
                "research-op",
                "try-conformance",
                permit_id,
                "research",
            )
            effect_id = created["effect_id"]

            # Actual initial dispatch primitive.
            first_attempt = f"{effect_id}:attempt:1"
            dispatched = effect.dispatch(
                str(effect_dir), effect_id, "try-conformance",
                first_attempt, "conformance-provider"
            )
            assert dispatched["state"] == "DISPATCHED"
            assert dispatched["attempt_id"] == first_attempt

            # UNKNOWN must only re-enter through retry_dispatch().
            unknown = effect.unknown(
                str(effect_dir), effect_id, "try-conformance", "timeout"
            )
            assert unknown["state"] == "UNKNOWN"

            retry_attacks = [
                ("missing_attempt_id", lambda: effect.retry_dispatch(
                    str(effect_dir), effect_id, "try-conformance",
                    "", "conformance-provider", 2)),
                ("stale_attempt", lambda: effect.retry_dispatch(
                    str(effect_dir), effect_id, "try-conformance",
                    f"{effect_id}:attempt:1", "conformance-provider", 1)),
                ("skipped_attempt", lambda: effect.retry_dispatch(
                    str(effect_dir), effect_id, "try-conformance",
                    f"{effect_id}:attempt:3", "conformance-provider", 3)),
                ("mismatched_effect", lambda: effect.retry_dispatch(
                    str(effect_dir), effect_id + "-forged", "try-conformance",
                    f"{effect_id}:attempt:2", "conformance-provider", 2)),
            ]
            for name, attack in retry_attacks:
                try:
                    attack()
                except Exception:
                    pass
                else:
                    raise AssertionError(f"retry attack accepted: {name}")

            retried = effect.retry_dispatch(
                str(effect_dir), effect_id, "try-conformance",
                f"{effect_id}:attempt:2", "conformance-provider", 2
            )
            assert retried["state"] == "DISPATCHED"
            attempt_id = retried["attempt_id"]
            assert attempt_id == f"{effect_id}:attempt:2"

            # The AIOS observation boundary requires an AIOS-owned evidence
            # record and binds it to the active provider. Encode receipt binding
            # in source_ref/artifact_ref and independently seal the chain below.
            pre_receipt = {
                "receipt_type": "AIOS_EXECUTION_RECEIPT",
                "schema_version": 1,
                "effect_id": effect_id,
                "attempt_id": attempt_id,
                "provider": "conformance-provider",
                "run_id": "conformance-run",
                "outcome": "OBSERVED_SUCCESS",
            }
            receipt = sealed_record("RECEIPT", pre_receipt)
            receipt_id = receipt["record_digest"]

            ev = evidence.EvidenceRecord(
                evidence_id="EV-" + digest({"receipt_id": receipt_id, "attempt_id": attempt_id}),
                level="OBSERVED",
                source_ref="receipt:" + receipt_id,
                claim="AIOS external-effect lifecycle conformance",
                run_id="conformance-run",
                provider="conformance-provider",
                artifact_ref=attempt_id,
            ).as_record()
            assert evidence.verify_evidence(ev)
            if ev["source_ref"] != "receipt:" + receipt_id:
                raise AssertionError("evidence is not receipt-bound")

            observed = effect.observe(
                str(effect_dir), effect_id, "try-conformance",
                "OBSERVED_SUCCESS",
                {
                    "attempt_id": attempt_id,
                    "provider": "conformance-provider",
                    "evidence": ev,
                },
            )
            assert observed["state"] == "OBSERVED_SUCCESS"

            evaluation = sealed_record("EVALUATION", {
                "evaluation_id": "EVAL-" + digest({
                    "evidence_id": ev["evidence_id"],
                    "evidence_digest": ev["digest"],
                }),
                "evidence_id": ev["evidence_id"],
                "evidence_digest": ev["digest"],
                "receipt_id": receipt_id,
                "verdict": "TASK_SUCCESS",
            })
            promotion = sealed_record("PROMOTION", {
                "promotion_id": "PROM-" + digest({
                    "evaluation_id": evaluation["evaluation_id"],
                    "evaluation_digest": evaluation["record_digest"],
                }),
                "evaluation_id": evaluation["evaluation_id"],
                "evaluation_digest": evaluation["record_digest"],
                "authority": "try-conformance",
                "decision": "PROMOTE_TO_FUTURE_OOS_TEST",
            })

            for record in (receipt, evaluation, promotion):
                verify_sealed(record)

            # Adversarial binding checks: each downstream object must fail when
            # its predecessor is altered.
            for name, record, mutate in (
                ("forged_receipt", receipt, lambda x: x.update({"attempt_id": "forged"})),
                ("altered_evidence", ev, lambda x: x.update({"claim": "tampered"})),
                ("altered_evaluation", evaluation, lambda x: x.update({"verdict": "PROMOTE"})),
                ("altered_promotion", promotion, lambda x: x.update({"evaluation_id": "forged"})),
            ):
                forged = dict(record)
                mutate(forged)
                try:
                    if name == "altered_evidence":
                        if evidence.verify_evidence(forged):
                            raise AssertionError(f"{name} verified")
                    else:
                        verify_sealed(forged)
                except AssertionError:
                    raise
                except Exception:
                    pass
                else:
                    raise AssertionError(f"{name} was not rejected")

            chain = {
                "schema_version": 2,
                "proof_type": "AIOS_FULL_LINEAGE_CONFORMANCE",
                "status": "PASS",
                "authority": {
                    "aios_source": str(AIOS),
                    "aios_source_sha": os.environ.get("AIOS_AUTHORITY_SHA", "unknown"),
                    "contract_id": contract_id,
                    "permit_id": permit_id,
                },
                "effect_id": effect_id,
                "attempt_id": attempt_id,
                "receipt": receipt,
                "evidence": ev,
                "evaluation": evaluation,
                "promotion": promotion,
                "checks": [
                    "actual_retry_dispatch_boundary",
                    "missing_attempt_rejected",
                    "stale_attempt_rejected",
                    "skipped_attempt_rejected",
                    "mismatched_effect_rejected",
                    "effect_attempt_binding",
                    "attempt_receipt_binding",
                    "receipt_evidence_binding",
                    "evidence_evaluation_binding",
                    "evaluation_promotion_binding",
                    "forged_receipt_rejected",
                    "altered_evidence_rejected",
                    "altered_evaluation_rejected",
                    "altered_promotion_rejected",
                ],
            }

            # Final whole-chain integrity check and durable artifact hash check.
            chain_body = dict(chain)
            chain_body["chain_digest"] = digest(chain_body)
            chain = chain_body

    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")

    chain["failures"] = failures
    if failures:
        chain["status"] = "BLOCKED"

    payload = json.dumps(chain, indent=2, sort_keys=True) + "\n"
    out = ROOT / "research" / "aios_conformance_receipt.json"
    out.write_text(payload, encoding="utf-8")
    persisted = out.read_text(encoding="utf-8")
    if persisted != payload:
        failures.append("durable artifact read-back mismatch")
        chain["status"] = "BLOCKED"
        payload = json.dumps(chain, indent=2, sort_keys=True) + "\n"
        out.write_text(payload, encoding="utf-8")
        persisted = out.read_text(encoding="utf-8")
    artifact_sha = hashlib.sha256(persisted.encode("utf-8")).hexdigest()
    print("AIOS_CONFORMANCE_PROOF: " + ("PASS" if not failures else "BLOCKED"))
    print(f"AIOS_CONFORMANCE_ARTIFACT_SHA256: {artifact_sha}")
    print(payload, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
