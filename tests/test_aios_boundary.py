import hashlib, json
from engine.aios_boundary import contract_identity, verify_authority


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def make_pair(tmp_path):
    contract={"contract_type":"EXECUTION_CONTRACT","task_id":"RESEARCH_BC7","scope":"research","actor":"research-controller","capabilities":["research_execute"],"input_digest":"sha256:data","allowed_effects":["write_research_evidence"],"evidence_required":["dataset_hash","validation_result"],"max_attempts":1,"terminal_states":["OOS_PASS","OOS_FAIL","HOLD"],"policy_digest":"sha256:policy"}
    cid=contract_identity(contract)
    permit={"permit_type":"EXECUTION_PERMIT","contract_id":cid,"task_id":contract["task_id"],"actor":contract["actor"],"capabilities":contract["capabilities"],"allowed_effects":contract["allowed_effects"],"max_attempts":contract["max_attempts"],"policy_digest":contract["policy_digest"],"issuer":"external-aios-authority"}
    permit["permit_id"]="PT-"+hashlib.sha256(canonical(permit).encode()).hexdigest()
    cp=tmp_path/"contract.json"; pp=tmp_path/"permit.json"
    cp.write_text(json.dumps(contract)); pp.write_text(json.dumps(permit))
    return cp,pp,contract,permit


def test_external_authority_verifies(tmp_path):
    cp,pp,_,_=make_pair(tmp_path)
    assert verify_authority(cp,pp)["task_id"] == "RESEARCH_BC7"


def test_capability_mutation_is_rejected(tmp_path):
    cp,pp,contract,permit=make_pair(tmp_path)
    permit["capabilities"]=["research_execute","live_trade"]
    pp.write_text(json.dumps(permit))
    try:
        verify_authority(cp,pp)
    except ValueError as exc:
        assert "identity mismatch" in str(exc) or "differs" in str(exc)
    else:
        raise AssertionError("forged capability must fail closed")
