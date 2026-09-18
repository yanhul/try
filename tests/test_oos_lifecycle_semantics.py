import pytest
from research.oos_lifecycle import OOSLifecycleError,OOSState,advance,assert_history_entry_legal,evaluate_oos,lifecycle_event,promotion_event,provider_failure_event

def result():
 return {"bc":306,"candidate_hash":"c306","oos_executed":True,"oos_selection_used":False,"oos_passed":False,"metrics":{"profit_factor":0.8},"dataset":{"sha256":"d306"},"protocol_sha256":"p306"}
def receipt():
 return {"schema_version":1,"receipt_type":"OOS_EXECUTION_RECEIPT","bc":306,"candidate_hash":"c306","dataset_sha256":"d306","protocol_sha256":"p306","oos_executed":True,"oos_selection_used":False,"oos_passed":False,"metrics":{"profit_factor":0.8},"result_sha256":"artifact-hash"}}

def test_promotion_is_pending_and_verdict_free():
 e=promotion_event(); assert e["oos_state"]=="OOS_PENDING" and e["oos_verdict"] is None; assert_history_entry_legal(e)

def test_verdict_requires_execution_receipt_and_evaluation():
 r=result(); r["oos_executed"]=False
 with pytest.raises(OOSLifecycleError,match="OOS_VERDICT_REQUIRES_EXECUTION"): evaluate_oos(r,receipt())

def test_verdict_cannot_be_history_authority_without_evaluation_event():
 with pytest.raises(OOSLifecycleError,match="OOS_VERDICT_REQUIRES_EVALUATION_EVENT"):
  assert_history_entry_legal({"oos_state":"OOS_EVALUATED","oos_verdict":"OOS_FAIL","oos_executed":True})

def test_provider_failure_never_becomes_oos_fail():
 e=provider_failure_event("provider_http_503"); assert e["oos_state"]=="PROVIDER_FAIL" and e["oos_verdict"] is None

def test_transition_graph_blocks_shortcut():
 assert advance(OOSState.OOS_RECEIPT,OOSState.OOS_EVALUATED)==OOSState.OOS_EVALUATED
 with pytest.raises(OOSLifecycleError): advance(OOSState.OOS_DISPATCHED,OOSState.OOS_FAIL)

def test_evaluation_binds_receipt():
 e=evaluate_oos(result(),receipt()); assert e["oos_verdict"]=="OOS_FAIL"; assert e["event_type"]=="OOS_EVALUATION"; assert e["receipt_digest"]
