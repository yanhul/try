"""Strict validation for hypotheses produced by the research agent."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
REQUIRED={"bc","parent_bc","hypothesis_id","conceptual_change","evidence_sources","rationale","is_testable","oos_selection_used"}
OPS={"identity","difference","ratio","zscore","rolling_mean","rolling_std","lag","delta","rank"}
COLS={"open","high","low","close","volume","volume_ratio","range_ratio","close_location","vwap_distance"}
WINDOW_REQUIRED={"zscore","rolling_mean","rolling_std","lag","delta","rank"}
def canonical_hash(candidate:dict)->str:
 payload={k:candidate[k] for k in sorted(candidate) if k!="candidate_hash"}
 return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def validate_candidate(candidate:dict,expected_bc:int,expected_parent:int)->tuple[bool,str]:
 missing=sorted(REQUIRED-candidate.keys())
 if missing:return False,f"missing_fields:{','.join(missing)}"
 if candidate["bc"]!=expected_bc or candidate["parent_bc"]!=expected_parent:return False,"bc_parent_mismatch"
 if not isinstance(candidate["conceptual_change"],str) or not candidate["conceptual_change"].strip():return False,"exactly_one_conceptual_change_required"
 if not isinstance(candidate["evidence_sources"],list) or not candidate["evidence_sources"] or any(not isinstance(x,str) or not x.strip() for x in candidate["evidence_sources"]):return False,"evidence_sources_required"
 if candidate["oos_selection_used"] is not False:return False,"oos_selection_forbidden"
 if candidate["is_testable"] is not True:return False,"not_testable"
 spec=candidate.get("discovery_spec")
 if candidate["hypothesis_id"]=="discovered_primitive" and not isinstance(spec,dict):return False,"discovery_spec_required"
 if spec is not None:
  if not isinstance(spec,dict) or spec.get("operator") not in OPS:return False,"invalid_discovery_operator"
  if spec.get("left") not in COLS:return False,"invalid_discovery_left_column"
  op=spec["operator"]
  if op in {"difference","ratio"} and spec.get("right") not in COLS:return False,"invalid_discovery_right_column"
  if op in WINDOW_REQUIRED:
   if not isinstance(spec.get("window"),int) or isinstance(spec.get("window"),bool) or spec["window"] not in {3,5,10,20,50,100}:return False,"invalid_discovery_window"
  if op in {"difference","ratio","zscore","rolling_mean","rolling_std","lag","delta","rank","identity"}:
   threshold=spec.get("threshold")
   if isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not math.isfinite(threshold) or not isinstance(spec.get("direction"),str) or spec["direction"] not in {"above","below"}: return False,"invalid_discovery_threshold"
 expected=canonical_hash(candidate); supplied=candidate.get("candidate_hash")
 if supplied is not None and supplied!=expected:return False,"candidate_hash_mismatch"
 candidate["candidate_hash"]=expected
 return True,expected
def load_candidate(path:Path,expected_bc:int,expected_parent:int)->dict:
 candidate=json.loads(path.read_text(encoding="utf-8")); ok,reason=validate_candidate(candidate,expected_bc,expected_parent)
 if not ok:raise ValueError(reason)
 return candidate
def write_candidate(path:Path,candidate:dict)->None:
 ok,reason=validate_candidate(candidate,int(candidate["bc"]),int(candidate["parent_bc"]))
 if not ok:raise ValueError(reason)
 path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(candidate,indent=2,sort_keys=True)+"\n",encoding="utf-8")
