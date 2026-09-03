"""AIOS execution-contract/permit verification boundary for research runs.

This module verifies a contract/permit supplied by an external authority. It
never issues permits and never changes policy, evidence requirements, or
terminal conditions. Missing authority material is a fail-closed condition for
consequential promotion/OOS execution.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

CONTRACT_TYPE = "EXECUTION_CONTRACT"
PERMIT_TYPE = "EXECUTION_PERMIT"
_REQUIRED = {"contract_type","task_id","scope","actor","capabilities","input_digest","allowed_effects","evidence_required","max_attempts","terminal_states","policy_digest"}
_PERMIT_REQUIRED = {"permit_type","permit_id","contract_id","task_id","actor","capabilities","allowed_effects","max_attempts","policy_digest","issuer"}

def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

def contract_identity(contract: dict) -> str:
    if set(contract) != _REQUIRED or contract.get("contract_type") != CONTRACT_TYPE:
        raise ValueError("contract schema/type mismatch")
    for k in ("task_id","scope","actor","input_digest","policy_digest"):
        if not isinstance(contract.get(k), str) or not contract[k].strip():
            raise ValueError(f"contract {k} invalid")
    for k in ("capabilities","allowed_effects","evidence_required","terminal_states"):
        if not isinstance(contract.get(k), list) or not all(isinstance(v,str) and v.strip() for v in contract[k]):
            raise ValueError(f"contract {k} invalid")
    if isinstance(contract.get("max_attempts"), bool) or not isinstance(contract.get("max_attempts"), int) or contract["max_attempts"] < 1:
        raise ValueError("contract max_attempts invalid")
    return "CT-" + hashlib.sha256(_canonical(contract).encode()).hexdigest()

def verify_permit(contract: dict, permit: dict) -> None:
    cid = contract_identity(contract)
    if set(permit) != _PERMIT_REQUIRED or permit.get("permit_type") != PERMIT_TYPE:
        raise ValueError("permit schema/type mismatch")
    if permit.get("contract_id") != cid:
        raise ValueError("permit is not bound to contract")
    expected = dict(permit); expected.pop("permit_id")
    if permit.get("permit_id") != "PT-" + hashlib.sha256(_canonical(expected).encode()).hexdigest():
        raise ValueError("permit identity mismatch")
    for k in ("task_id","actor","capabilities","allowed_effects","max_attempts","policy_digest"):
        if permit.get(k) != contract.get(k):
            raise ValueError(f"permit/{k} differs from contract")

def verify_authority(contract_path: str | Path, permit_path: str | Path) -> dict:
    contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    permit = json.loads(Path(permit_path).read_text(encoding="utf-8"))
    verify_permit(contract, permit)
    return {"contract_id": contract_identity(contract), "issuer": permit["issuer"], "task_id": contract["task_id"], "actor": contract["actor"]}
