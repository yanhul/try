"""TRY execution boundary backed by the shared AIOS authority primitives.

TRY owns research semantics; AIOS owns contract/permit/attestation validation.
This module is intentionally a thin compatibility adapter and contains no
second implementation of the authority rules.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path


def _aios_modules(aios_root: str | Path | None = None):
    configured = aios_root or os.environ.get("AIOS_ROOT") or os.environ.get("AIOS_SOURCE")
    if not configured:
        raise FileNotFoundError("AIOS_ROOT/AIOS_SOURCE is not configured")
    root = Path(configured).expanduser().resolve()
    if not (root / "core" / "contract.py").is_file():
        raise FileNotFoundError(f"AIOS contract module not found under {root}")
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return importlib.import_module("core.contract"), importlib.import_module("core.attestation")


def contract_identity(contract, *, aios_root=None):
    contract_mod, _ = _aios_modules(aios_root)
    return contract_mod.contract_identity(contract)


def verify_permit(contract, permit, *, aios_root=None):
    contract_mod, _ = _aios_modules(aios_root)
    return contract_mod.verify_permit(contract, permit)


def verify_attestation(contract, permit, attestation, secret, *, aios_root=None):
    _, attestation_mod = _aios_modules(aios_root)
    return attestation_mod.verify_attestation(contract, permit, attestation, secret)


def verify_authority(contract_path, permit_path, attestation_path=None, secret=None, *, aios_root=None):
    contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    permit = json.loads(Path(permit_path).read_text(encoding="utf-8"))
    verify_permit(contract, permit, aios_root=aios_root)
    if attestation_path is not None:
        verify_attestation(
            contract,
            permit,
            json.loads(Path(attestation_path).read_text(encoding="utf-8")),
            secret or "",
            aios_root=aios_root,
        )
    return {
        "contract_id": contract_identity(contract, aios_root=aios_root),
        "issuer": permit["issuer"],
        "task_id": contract["task_id"],
        "actor": contract["actor"],
        "attested": attestation_path is not None,
        "authority_provider": "AIOS.core.contract+attestation",
    }


__all__ = ["contract_identity", "verify_permit", "verify_attestation", "verify_authority"]
