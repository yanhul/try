#!/usr/bin/env python3
"""Verify externally provisioned AIOS repair authority in an isolated process.

This step is intentionally separate from the repair controller. The independent
Git-backed verifier validates the issuer HMAC; this step checks the persisted AIOS
records and local authorization without ever receiving the issuer's HMAC secret.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _record_digest(root: Path, kind: str, record_id: str) -> str:
    # IDs are filenames, never caller-controlled path fragments.
    import re
    if kind not in {"contracts", "permits", "attestations"}:
        raise RuntimeError("authority_record_kind_invalid")
    if not isinstance(record_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", record_id):
        raise RuntimeError("authority_record_id_invalid")
    root = root.resolve()
    authority_root = (root / "authority").resolve()
    try:
        authority_root.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("authority_directory_path_escape") from exc
    directory = (authority_root / kind).resolve()
    try:
        directory.relative_to(authority_root)
    except ValueError as exc:
        raise RuntimeError(f"authority_record_directory_escape:{kind}") from exc
    path = (directory / f"{record_id}.json").resolve()
    try:
        path.relative_to(directory)
    except ValueError as exc:
        raise RuntimeError(f"authority_record_path_escape:{kind}") from exc
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_and_write_receipt() -> Path:
    authority_dir = os.environ.get("AIOS_REPAIR_AUTHORITY_DIR", "").strip()
    contract_id = os.environ.get("AIOS_REPAIR_CONTRACT_ID", "").strip()
    permit_id = os.environ.get("AIOS_REPAIR_PERMIT_ID", "").strip()
    attestation_verified = os.environ.get("AIOS_REPAIR_ATTESTATION_VERIFIED", "").strip()
    store_commit_sha = os.environ.get("AIOS_REPAIR_AUTHORITY_STORE_COMMIT_SHA", "").strip()
    run_id = os.environ.get("AIOS_REPAIR_RUN_ID", "").strip()
    receipt_raw = os.environ.get("AIOS_REPAIR_AUTHORITY_GATE_RECEIPT", "").strip()
    runner_temp = os.environ.get("RUNNER_TEMP", "").strip()
    if not all((authority_dir, contract_id, permit_id, run_id, receipt_raw, runner_temp)) or attestation_verified != "true":
        raise RuntimeError("external_authority_gate_configuration_missing")
    if not re.fullmatch(r"[0-9a-f]{40}", store_commit_sha):
        raise RuntimeError("authority_store_commit_sha_invalid")
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", contract_id):
        raise RuntimeError("authority_contract_id_invalid")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", permit_id):
        raise RuntimeError("authority_permit_id_invalid")
    if not run_id.isdecimal():
        raise RuntimeError("external_authority_gate_run_id_invalid")

    root = Path(authority_dir).expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError("authority_directory_missing")
    if any(part.lower() in {"tmp", "temp", "temporary"} for part in root.parts):
        raise RuntimeError("authority_directory_must_not_be_temporary")

    receipt_path = Path(receipt_raw).resolve()
    temp_root = Path(runner_temp).resolve()
    if receipt_path.parent != temp_root:
        raise RuntimeError("authority_gate_receipt_must_be_in_runner_temp")

    from core.authority import authorize, load_attestation, load_contract, load_permit

    authorize(str(root), contract_id, permit_id)
    contract = load_contract(str(root), contract_id)
    permit = load_permit(str(root), permit_id)
    attestation = load_attestation(str(root), permit_id)
    if not isinstance(contract, dict):
        raise RuntimeError("contract_record_type_invalid")
    if not isinstance(permit, dict):
        raise RuntimeError("permit_record_type_invalid")
    if not isinstance(attestation, dict):
        raise RuntimeError("attestation_record_type_invalid")
    if (attestation.get("attestation_type") != "EXECUTION_PERMIT_ATTESTATION"
            or attestation.get("algorithm") != "HMAC-SHA256"
            or attestation.get("contract_id") != contract_id
            or attestation.get("permit_id") != permit_id
            or attestation.get("issuer") != "yanhul/aios-authority-store"):
        raise RuntimeError("authority_attestation_identity_invalid")

    if contract.get("task_id") != f"try-ci-repair-{run_id}":
        raise RuntimeError("contract_task_id_mismatch")
    if contract.get("actor") != "try-autonomous-repair":
        raise RuntimeError("contract_actor_mismatch")
    if contract.get("scope") != "repository":
        raise RuntimeError("contract_scope_mismatch")
    capabilities = contract.get("capabilities")
    if not isinstance(capabilities, list) or any(not isinstance(item, str) for item in capabilities):
        raise RuntimeError("contract_capabilities_type_invalid")
    if "repo_patch@1" not in capabilities:
        raise RuntimeError("contract_patch_capability_missing")
    allowed_effects = contract.get("allowed_effects")
    if not isinstance(allowed_effects, list) or any(not isinstance(item, str) for item in allowed_effects):
        raise RuntimeError("contract_allowed_effects_type_invalid")
    if "external_effect" not in allowed_effects:
        raise RuntimeError("contract_patch_effect_not_allowed")
    budget = contract.get("max_attempts")
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 3:
        raise RuntimeError("contract_attempt_budget_exceeds_runner_limit")

    receipt = {
        "schema": 1,
        "verified": True,
        "run_id": run_id,
        "authority_root": str(root),
        "contract_id": contract_id,
        "permit_id": permit_id,
        "contract_sha256": _record_digest(root, "contracts", contract_id),
        "permit_sha256": _record_digest(root, "permits", permit_id),
        "attestation_sha256": _record_digest(root, "attestations", permit_id),
        "attestation_verified_by": "independent-git-authority-verifier",
        "authority_store_commit_sha": store_commit_sha,
    }
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    return receipt_path


if __name__ == "__main__":
    path = verify_and_write_receipt()
    print(json.dumps({"status": "VERIFIED", "receipt": str(path)}, sort_keys=True))
