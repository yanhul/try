#!/usr/bin/env python3
"""Fail-closed AIOS conformance proof for the child research harness.

This is a runtime proof, not a string-presence check.  The pinned AIOS
authority checkout is exercised in temporary state and the resulting receipt
is persisted for lineage.
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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_aios_package():
    if not AIOS.is_dir():
        raise RuntimeError(f"AIOS_SOURCE missing: {AIOS}")
    # Load the package modules from the pinned checkout without modifying it.
    import sys
    sys.path.insert(0, str(AIOS))
    from core import contract, effect_authority, evidence
    return contract, effect_authority, evidence


def main() -> int:
    contract, effect, evidence = load_aios_package()
    failures: list[str] = []

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

    try:
        contract.validate_contract(sample)
        cid = contract.contract_identity(sample)
        permit = contract.issue_permit(sample, "aios-conformance")
        contract.verify_permit(sample, permit)
    except Exception as exc:
        failures.append(f"contract/permit: {type(exc).__name__}: {exc}")
        cid = ""

    try:
        with tempfile.TemporaryDirectory() as td:
            effect_dir = Path(td)
            created = effect.create_effect(str(effect_dir), cid, "research-op", "try")
            effect_id = created["effect_id"]

            dispatched = effect.dispatch(
                str(effect_dir), effect_id, "try",
                f"{effect_id}:attempt:1", "conformance-provider"
            )
            if dispatched["state"] != "DISPATCHED":
                raise AssertionError("initial dispatch did not produce DISPATCHED")

            unknown = effect.unknown(str(effect_dir), effect_id, "try", "timeout")
            if unknown["state"] != "UNKNOWN":
                raise AssertionError("timeout did not produce UNKNOWN")

            # The generic transition graph must reject UNKNOWN -> DISPATCHED.
            try:
                effect.transition(
                    str(effect_dir), effect_id, "DISPATCHED", "try",
                    attempt=2, attempt_id=f"{effect_id}:attempt:2",
                    provider="conformance-provider",
                )
            except Exception:
                pass
            else:
                raise AssertionError("generic UNKNOWN -> DISPATCHED bypass was accepted")

            # The dedicated retry boundary must fence the attempt number.
            try:
                effect.retry_dispatch(
                    str(effect_dir), effect_id, "try",
                    f"{effect_id}:attempt:3", "conformance-provider", 3
                )
            except Exception:
                pass
            else:
                raise AssertionError("retry attempt fence accepted a skipped attempt")

            retried = effect.retry_dispatch(
                str(effect_dir), effect_id, "try",
                f"{effect_id}:attempt:2", "conformance-provider", 2
            )
            if retried["state"] != "DISPATCHED" or retried["attempt"] != 2:
                raise AssertionError("valid retry did not preserve fenced lineage")

            observed = effect.observe(
                str(effect_dir), effect_id, "try", "OBSERVED_SUCCESS",
                {"run_id": "conformance-run", "result": "ok"}
            )
            if observed["state"] != "OBSERVED_SUCCESS":
                raise AssertionError("observation did not reach OBSERVED_SUCCESS")

            receipt = evidence.EvidenceRecord(
                evidence_id="EV-CONFORMANCE-001",
                level="OBSERVED",
                source_ref="effect:" + effect_id,
                claim="AIOS external-effect lifecycle conformance",
                run_id="conformance-run",
                provider="conformance-provider",
                artifact_ref=effect_id,
            ).as_record()
            if not evidence.verify_evidence(receipt):
                raise AssertionError("valid evidence receipt did not verify")
            tampered = dict(receipt)
            tampered["claim"] = "tampered"
            if evidence.verify_evidence(tampered):
                raise AssertionError("tampered evidence receipt verified")

    except Exception as exc:
        failures.append(f"effect/evidence lineage: {type(exc).__name__}: {exc}")

    proof = {
        "schema_version": 1,
        "proof_type": "AIOS_CONFORMANCE_PROOF",
        "status": "PASS" if not failures else "BLOCKED",
        "aios_source": str(AIOS),
        "aios_source_sha": os.environ.get("AIOS_AUTHORITY_SHA", "unknown"),
        "checks": [
            "contract_validation",
            "permit_binding",
            "effect_create_dispatch",
            "unknown_fail_closed",
            "retry_attempt_fence",
            "observed_terminal_effect",
            "evidence_digest",
            "evidence_tamper_rejection",
        ],
        "failures": failures,
    }
    payload = json.dumps(proof, indent=2, sort_keys=True) + "\n"
    out = ROOT / "research" / "aios_conformance_receipt.json"
    out.write_text(payload, encoding="utf-8")
    print("AIOS_CONFORMANCE_PROOF: " + ("PASS" if not failures else "BLOCKED"))
    print(payload, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
