import importlib.util

def gate():
    spec = importlib.util.spec_from_file_location("gate3", "audit_bc3_fast_gate.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def candidate():
    c={"bc":3,"parent_bc":2,"hypothesis_id":"sweep_confirmation","conceptual_change":"one change","evidence_sources":["research/failure_analysis/BC2.json"],"rationale":"test","is_testable":True,"oos_selection_used":False}
    c["candidate_hash"]=gate().canonical_hash(c); return c

def evidence(c):
    return {"schema_version":10,"bc":3,"parent_bc":2,"hypothesis_id":c["hypothesis_id"],"candidate_hash":c["candidate_hash"],"oos_selection_used":False,"oos_executed":False,"validation_passed":True,"gross_validation_passed":True,"validation_basis":"NET_REQUIRED_FOR_PROMOTION","net_validation_gate":"PASS","dataset":{"sha256":"d"*64},"VALIDATION":{"metrics":{"trade_count":20,"win_count":12,"loss_count":8,"win_rate":0.6,"total_return":0.02,"avg_return":0.001,"profit_factor":1.2,"max_drawdown":0.1}}}

def test_gate3_accepts_bound_evidence():
    ok,reason=gate().validate_gate3(candidate(),evidence(candidate())); assert ok and reason=="PROMOTE_TO_FUTURE_OOS_TEST"

def test_gate3_rejects_candidate_hash_mutation():
    c=candidate(); e=evidence(c); e["candidate_hash"]="0"*64; assert gate().validate_gate3(c,e)==(False,"candidate_hash_mismatch")

def test_gate3_rejects_validation_pass_mutation():
    c=candidate(); e=evidence(c); e["validation_passed"]=False; assert gate().validate_gate3(c,e)==(False,"validation_gate_inconsistent")

def test_gate3_rejects_oos_contamination():
    c=candidate(); e=evidence(c); e["oos_selection_used"]=True; assert gate().validate_gate3(c,e)==(False,"oos_selection_forbidden")

def test_gate3_rejects_metric_mutation():
    c=candidate(); e=evidence(c); e["VALIDATION"]["metrics"]["trade_count"]=19; assert gate().validate_gate3(c,e)==(False,"validation_gate_inconsistent")

def test_gate3_rejects_identity_mutation():
    c=candidate(); e=evidence(c); e["hypothesis_id"]="quiet_retest"; assert gate().validate_gate3(c,e)==(False,"hypothesis_identity_mismatch")

def test_gate3_rejects_execution_before_oos_authority():
    c=candidate(); e=evidence(c); e["oos_executed"]=True; assert gate().validate_gate3(c,e)==(False,"oos_execution_forbidden")

def test_gate3_rejects_unexecutable_hypothesis():
    c = candidate(); e = evidence(c); c["hypothesis_id"] = "not_registered"; c["candidate_hash"] = gate().canonical_hash(c); e["candidate_hash"] = c["candidate_hash"]; e["hypothesis_id"] = c["hypothesis_id"]; assert gate().validate_gate3(c,e)==(False,"unexecutable_hypothesis_id")
