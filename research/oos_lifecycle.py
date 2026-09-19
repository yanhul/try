"""Canonical OOS lifecycle and verdict authority gate."""
from __future__ import annotations
from enum import StrEnum
from typing import Any
import hashlib, json

class OOSLifecycleError(ValueError):
    pass

class OOSState(StrEnum):
    VALIDATION_PASS="VALIDATION_PASS"
    OOS_AUTHORIZED="OOS_AUTHORIZED"
    OOS_DISPATCHED="OOS_DISPATCHED"
    OOS_EXECUTED="OOS_EXECUTED"
    OOS_RECEIPT="OOS_RECEIPT"
    OOS_EVALUATED="OOS_EVALUATED"
    OOS_PENDING="OOS_PENDING"
    OOS_PASS="OOS_PASS"
    OOS_FAIL="OOS_FAIL"
    PROVIDER_FAIL="PROVIDER_FAIL"
    UNKNOWN="UNKNOWN"
    BLOCKED="BLOCKED"

_TRANSITIONS={
 OOSState.VALIDATION_PASS:frozenset({OOSState.OOS_AUTHORIZED}),
 OOSState.OOS_AUTHORIZED:frozenset({OOSState.OOS_DISPATCHED,OOSState.BLOCKED}),
 OOSState.OOS_DISPATCHED:frozenset({OOSState.OOS_EXECUTED,OOSState.PROVIDER_FAIL,OOSState.UNKNOWN}),
 OOSState.OOS_EXECUTED:frozenset({OOSState.OOS_RECEIPT,OOSState.UNKNOWN}),
 OOSState.OOS_RECEIPT:frozenset({OOSState.OOS_EVALUATED,OOSState.UNKNOWN}),
 OOSState.OOS_EVALUATED:frozenset({OOSState.OOS_PASS,OOSState.OOS_FAIL}),
 OOSState.PROVIDER_FAIL:frozenset({OOSState.UNKNOWN,OOSState.OOS_DISPATCHED,OOSState.BLOCKED}),
 OOSState.UNKNOWN:frozenset({OOSState.OOS_AUTHORIZED,OOSState.BLOCKED}),
 OOSState.BLOCKED:frozenset(), OOSState.OOS_PASS:frozenset(), OOSState.OOS_FAIL:frozenset(),
 OOSState.OOS_PENDING:frozenset({OOSState.OOS_AUTHORIZED,OOSState.BLOCKED}),
}

def advance(current: OOSState|str,target: OOSState|str)->OOSState:
 current,target=OOSState(current),OOSState(target)
 if target not in _TRANSITIONS[current]: raise OOSLifecycleError(f"ILLEGAL_OOS_TRANSITION:{current}->{target}")
 return target

def promotion_event()->dict[str,Any]:
 return {"decision":"PROMOTE_TO_FUTURE_OOS_TEST","oos_state":"OOS_PENDING","oos_verdict":None,"oos_executed":False}

def lifecycle_event(state:OOSState|str,*,bc:int,candidate_hash:str,**extra:Any)->dict[str,Any]:
 state=OOSState(state)
 if state in {OOSState.OOS_PASS,OOSState.OOS_FAIL,OOSState.OOS_EVALUATED}: raise OOSLifecycleError("LIFECYCLE_EVENT_CANNOT_MANUFACTURE_EVALUATION")
 event={"bc":int(bc),"candidate_hash":candidate_hash,"oos_state":state.value,"oos_verdict":None,"oos_executed":state in {OOSState.OOS_EXECUTED,OOSState.OOS_RECEIPT}}
 event.update(extra)
 assert_history_entry_legal(event)
 return event

def provider_failure_event(reason:str)->dict[str,Any]:
 return {"oos_state":"PROVIDER_FAIL","oos_verdict":None,"oos_executed":False,"provider_failure_reason":str(reason)}

def _require_receipt_binding(result,receipt):
 if result.get("oos_executed") is not True: raise OOSLifecycleError("OOS_VERDICT_REQUIRES_EXECUTION")
 if not receipt: raise OOSLifecycleError("OOS_VERDICT_REQUIRES_RECEIPT")
 for key in ("bc","candidate_hash","dataset_sha256","protocol_sha256"):
  expected=result.get("dataset",{}).get("sha256") if key=="dataset_sha256" else result.get(key)
  if receipt.get(key)!=expected: raise OOSLifecycleError(f"OOS_RECEIPT_BINDING_MISMATCH:{key}")
 if receipt.get("receipt_type")!="OOS_EXECUTION_RECEIPT": raise OOSLifecycleError("OOS_RECEIPT_TYPE")
 if receipt.get("schema_version")!=1: raise OOSLifecycleError("OOS_RECEIPT_SCHEMA")
 if receipt.get("oos_executed") is not True: raise OOSLifecycleError("OOS_RECEIPT_REQUIRES_EXECUTION")
 if receipt.get("oos_selection_used") is not False: raise OOSLifecycleError("OOS_RECEIPT_SELECTION_CONTAMINATION")
 if not receipt.get("receipt_id"): raise OOSLifecycleError("OOS_RECEIPT_ID_MISSING")
 if receipt.get("metrics")!=result.get("metrics"): raise OOSLifecycleError("OOS_RECEIPT_METRICS_MISMATCH")

def evaluate_oos(result,receipt):
 _require_receipt_binding(result,receipt)
 if receipt.get("result_sha256") is None:
  raise OOSLifecycleError("OOS_RECEIPT_RESULT_BINDING_MISSING")
 passed=result.get("oos_passed")
 if not isinstance(passed,bool): raise OOSLifecycleError("OOS_EVALUATION_VERDICT_MISSING")
 verdict="OOS_PASS" if passed else "OOS_FAIL"
 digest=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 return {"event_type":"OOS_EVALUATION","oos_state":"OOS_EVALUATED","oos_verdict":verdict,"oos_executed":True,"receipt_type":receipt["receipt_type"],"receipt_schema_version":receipt["schema_version"],"bc":result["bc"],"candidate_hash":result["candidate_hash"],"receipt_digest":digest}

def terminal_reason_from_oos(result,receipt):
 return evaluate_oos(result,receipt)["oos_verdict"]

def assert_history_entry_legal(entry):
 if not isinstance(entry,dict): raise OOSLifecycleError("HISTORY_ENTRY_INVALID")
 decision,verdict,executed,state=entry.get("decision"),entry.get("oos_verdict"),entry.get("oos_executed"),entry.get("oos_state")
 if decision=="PROMOTE_TO_FUTURE_OOS_TEST":
  if verdict is not None: raise OOSLifecycleError("PROMOTION_MUST_NOT_CARRY_OOS_VERDICT")
  if executed is not False: raise OOSLifecycleError("PROMOTION_MUST_BE_PRE_OOS")
  if state!="OOS_PENDING": raise OOSLifecycleError("PROMOTION_STATE_MUST_BE_OOS_PENDING")
 if state in {"OOS_EXECUTED","OOS_RECEIPT"} and entry.get("oos_executed") is not True:
  raise OOSLifecycleError("OOS_EXECUTED_STATE_REQUIRES_EXECUTION")
 if state=="OOS_RECEIPT":
  if not entry.get("receipt_type") or entry.get("receipt_schema_version")!=1 or not entry.get("receipt_id"):
   raise OOSLifecycleError("OOS_RECEIPT_STATE_REQUIRES_RECEIPT_BINDING")
 if verdict is not None:
  if entry.get("event_type")!="OOS_EVALUATION": raise OOSLifecycleError("OOS_VERDICT_REQUIRES_EVALUATION_EVENT")
  if not entry.get("receipt_digest"): raise OOSLifecycleError("OOS_VERDICT_REQUIRES_RECEIPT_BINDING")
  if verdict not in {"OOS_PASS","OOS_FAIL"}: raise OOSLifecycleError("UNKNOWN_OOS_VERDICT")
  if executed is not True: raise OOSLifecycleError("OOS_VERDICT_REQUIRES_EXECUTION")
  if state!="OOS_EVALUATED": raise OOSLifecycleError("OOS_VERDICT_REQUIRES_EVALUATION_STATE")
