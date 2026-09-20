"""Strict validation for hypotheses produced by the research agent."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
REQUIRED={"bc","parent_bc","hypothesis_id","conceptual_change","evidence_sources","rationale","is_testable","oos_selection_used"}
OPS={"identity","difference","ratio","zscore","rolling_mean","rolling_std","lag","delta","rank"}
COLS={"open","high","low","close","volume","volume_ratio","range_ratio","close_location","vwap_distance","momentum_trend","mean_reversion","volatility","wyckoff_vsa_vpa","vwap_volume_profile","regime","seasonality","point_figure","gann_reference"}
MECHANISM_FAMILIES={"momentum_trend","mean_reversion","volatility","smc_ict","fvg_imbalance","wyckoff_vsa_vpa","vwap_volume_profile","regime","seasonality","point_figure","gann_reference"}
# Families listed in the source taxonomy but not executable as directional predicates.
NON_DIRECTIONAL_MECHANISM_FAMILIES={"volatility","seasonality"}
EXECUTABLE_MECHANISM_FAMILIES=MECHANISM_FAMILIES-NON_DIRECTIONAL_MECHANISM_FAMILIES
# Family-specific executable vocabulary. This is a search-quality guard, not a performance claim.
# A source family may translate to a BTC-compatible proxy, but only through primitives
# whose observable inputs/operators are explicitly admissible for that family.
FAMILY_PRIMITIVES={
 "momentum_trend":{"ops":{"identity","difference","delta","lag","rolling_mean"},"cols":{"open","high","low","close","volume","momentum_trend"}},
 "mean_reversion":{"ops":{"difference","ratio","zscore","rolling_mean","rolling_std","delta"},"cols":{"close","vwap_distance","range_ratio","volume_ratio"}},
 "smc_ict":{"ops":{"difference","delta","lag"},"cols":{"high","low","close","close_location","range_ratio"}},
 "fvg_imbalance":{"ops":{"difference","delta","lag"},"cols":{"high","low","close","close_location","range_ratio"}},
 "wyckoff_vsa_vpa":{"ops":{"difference","ratio","delta","lag","rolling_mean","zscore"},"cols":{"open","high","low","close","volume","volume_ratio","range_ratio","close_location"}},
 "vwap_volume_profile":{"ops":{"difference","ratio","zscore","rolling_mean","rolling_std","delta"},"cols":{"close","volume","volume_ratio","vwap_distance","range_ratio"}},
 "regime":{"ops":{"difference","ratio","zscore","rolling_mean","rolling_std","lag","delta"},"cols":{"close","volume","volume_ratio","range_ratio","vwap_distance"}},
 "point_figure":{"ops":{"difference","delta","lag","rolling_mean"},"cols":{"open","high","low","close","range_ratio"}},
 "gann_reference":{"ops":{"difference","delta","lag","rolling_mean"},"cols":{"open","high","low","close"}},
}
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
 if candidate["hypothesis_id"]=="mechanism_family":
  if not isinstance(spec,dict) or spec.get("mechanism_family") not in MECHANISM_FAMILIES:return False,"invalid_mechanism_family"
  if spec.get("mechanism_family") in NON_DIRECTIONAL_MECHANISM_FAMILIES:return False,"non_directional_mechanism_family"
  threshold=spec.get("threshold")
  if isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not math.isfinite(threshold):return False,"invalid_discovery_threshold"
  if spec.get("direction") not in {"above","below"}:return False,"invalid_discovery_threshold"
 elif candidate["hypothesis_id"]=="discovered_primitive" and not isinstance(spec,dict):return False,"discovery_spec_required"
 if spec is not None and candidate["hypothesis_id"]!="mechanism_family":
  family=spec.get("mechanism_family")
  if family is not None:
   if family not in EXECUTABLE_MECHANISM_FAMILIES:return False,"invalid_primitive_mechanism_family"
   profile=FAMILY_PRIMITIVES.get(family)
   if profile is None:return False,"missing_family_primitive_profile"
   if spec.get("operator") not in profile["ops"]:return False,"family_operator_not_admissible"
   if spec.get("left") not in profile["cols"]:return False,"family_left_column_not_admissible"
   if spec.get("right") is not None and spec.get("right") not in profile["cols"]:return False,"family_right_column_not_admissible"
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
