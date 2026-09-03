"""AIOS execution-contract/permit/attestation verification boundary."""
from __future__ import annotations
import hashlib, hmac, json
from pathlib import Path

CONTRACT_TYPE="EXECUTION_CONTRACT"; PERMIT_TYPE="EXECUTION_PERMIT"; ATTESTATION_TYPE="EXECUTION_PERMIT_ATTESTATION"
_REQUIRED={"contract_type","task_id","scope","actor","capabilities","input_digest","allowed_effects","evidence_required","max_attempts","terminal_states","policy_digest"}
_PERMIT_REQUIRED={"permit_type","permit_id","contract_id","task_id","actor","capabilities","allowed_effects","max_attempts","policy_digest","issuer"}
_ATTESTATION_REQUIRED={"attestation_type","contract_id","permit_id","issuer","algorithm","signature"}

def _canonical(obj): return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True)

def contract_identity(contract):
    if set(contract)!=_REQUIRED or contract.get("contract_type")!=CONTRACT_TYPE: raise ValueError("contract schema/type mismatch")
    for k in ("task_id","scope","actor","input_digest","policy_digest"):
        if not isinstance(contract.get(k),str) or not contract[k].strip(): raise ValueError(f"contract {k} invalid")
    for k in ("capabilities","allowed_effects","evidence_required","terminal_states"):
        if not isinstance(contract.get(k),list) or not all(isinstance(v,str) and v.strip() for v in contract[k]): raise ValueError(f"contract {k} invalid")
    if isinstance(contract.get("max_attempts"),bool) or not isinstance(contract.get("max_attempts"),int) or contract["max_attempts"]<1: raise ValueError("contract max_attempts invalid")
    return "CT-"+hashlib.sha256(_canonical(contract).encode("utf-8")).hexdigest()

def verify_permit(contract,permit):
    cid=contract_identity(contract)
    if set(permit)!=_PERMIT_REQUIRED or permit.get("permit_type")!=PERMIT_TYPE: raise ValueError("permit schema/type mismatch")
    if permit.get("contract_id")!=cid: raise ValueError("permit is not bound to contract")
    expected=dict(permit); expected.pop("permit_id")
    if permit.get("permit_id")!="PT-"+hashlib.sha256(_canonical(expected).encode("utf-8")).hexdigest(): raise ValueError("permit identity mismatch")
    for k in ("task_id","actor","capabilities","allowed_effects","max_attempts","policy_digest"):
        if permit.get(k)!=contract.get(k): raise ValueError(f"permit/{k} differs from contract")

def verify_attestation(contract,permit,attestation,secret):
    if not isinstance(secret,str) or not secret: raise ValueError("missing authority attestation secret")
    verify_permit(contract,permit)
    if set(attestation)!=_ATTESTATION_REQUIRED: raise ValueError("attestation schema mismatch")
    if attestation.get("attestation_type")!=ATTESTATION_TYPE or attestation.get("algorithm")!="HMAC-SHA256": raise ValueError("attestation type/algorithm mismatch")
    if (attestation.get("contract_id"),attestation.get("permit_id"),attestation.get("issuer"))!=(permit["contract_id"],permit["permit_id"],permit["issuer"]): raise ValueError("attestation is not bound to permit")
    msg=f"{permit['contract_id']}\n{permit['permit_id']}\n{permit['issuer']}".encode("utf-8")
    expected=hmac.new(secret.encode("utf-8"),msg,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(attestation.get("signature",""),expected): raise ValueError("attestation signature mismatch")

def verify_authority(contract_path,permit_path,attestation_path=None,secret=None):
    contract=json.loads(Path(contract_path).read_text(encoding="utf-8")); permit=json.loads(Path(permit_path).read_text(encoding="utf-8")); verify_permit(contract,permit)
    if attestation_path is not None: verify_attestation(contract,permit,json.loads(Path(attestation_path).read_text(encoding="utf-8")),secret or "")
    return {"contract_id":contract_identity(contract),"issuer":permit["issuer"],"task_id":contract["task_id"],"actor":contract["actor"],"attested":attestation_path is not None}
