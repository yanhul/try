"""Read-only verification of externally issued AIOS research authority.

This module can verify binding but cannot mint or broaden a contract/permit.
The actual governing authority remains outside this repository.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

FIELDS = (
    "contract_type", "task_id", "scope", "actor", "capabilities",
    "input_digest", "allowed_effects", "evidence_required", "max_attempts",
    "terminal_states", "policy_digest",
)
PERMIT_FIELDS = (
    "permit_type", "permit_id", "contract_id", "task_id", "actor",
    "capabilities", "allowed_effects", "max_attempts", "policy_digest", "issuer",
)


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def verify_external_authority(authority_dir: str | Path, contract_id: str, permit_id: str) -> dict:
    root = Path(authority_dir)
    cp = root / "contracts" / f"{contract_id}.json"
    pp = root / "permits" / f"{permit_id}.json"
    if not cp.exists() or not pp.exists():
        raise ValueError("AIOS authority record missing")
    contract_record = json.loads(cp.read_text(encoding="utf-8"))
    permit = json.loads(pp.read_text(encoding="utf-8"))
    contract = {k: contract_record[k] for k in FIELDS}
    if "record_type" not in contract_record or contract_record["record_type"] != "EXECUTION_CONTRACT":
        raise ValueError("AIOS contract record type mismatch")
    expected_cid = "CT-" + sha(contract)
    if expected_cid != contract_id or contract_record.get("contract_id") != contract_id:
        raise ValueError("AIOS contract identity mismatch")
    if set(permit) != set(PERMIT_FIELDS) or permit.get("permit_type") != "EXECUTION_PERMIT":
        raise ValueError("AIOS permit schema mismatch")
    if permit.get("contract_id") != contract_id:
        raise ValueError("AIOS permit/contract binding mismatch")
    unsigned = dict(permit)
    actual_pid = unsigned.pop("permit_id", None)
    if actual_pid != "PT-" + sha(unsigned) or actual_pid != permit_id:
        raise ValueError("AIOS permit identity mismatch")
    for field in ("task_id", "actor", "capabilities", "allowed_effects", "max_attempts", "policy_digest"):
        if permit[field] != contract[field]:
            raise ValueError(f"AIOS permit/{field} mismatch")
    return contract
