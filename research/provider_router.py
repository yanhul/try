#!/usr/bin/env python3
from __future__ import annotations
import json,math,os,random,sys,time,datetime,urllib.error,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.autonomous_hypothesis import write_candidate,validate_candidate,MECHANISM_FAMILIES,EXECUTABLE_MECHANISM_FAMILIES,FAMILY_PRIMITIVES
from research.evidence_calibration import verify_with_openai_compatible
from research.btc_translation_policy import eligible_survivors
from research.hypothesis_novelty import structural_key,novelty_metadata
from research.search_memory import rank_families,note_selection
OPERATORS=["identity","difference","ratio","zscore","rolling_mean","rolling_std","lag","delta","rank"]
COLUMNS=["open","high","low","close","volume","volume_ratio","range_ratio","close_location","vwap_distance"]
WINDOWS=[3,5,10,20,50,100]
SYSTEM=f'''Translate ONLY the SELECTED BTC-COMPATIBLE SCREEN SURVIVOR. You are not a selector. Use only BTCUSDT 1H OHLCV. Never use OOS, expected performance, stars or intuition as evidence. Valid families: {sorted(MECHANISM_FAMILIES)}. A mechanism_family hypothesis MUST use exactly SELECTED_SURVIVOR_FAMILY. discovered_primitive may use only operators {OPERATORS} and columns {COLUMNS}. Threshold/window are parameters, NOT novelty. New hypotheses must change family/operator/left/right/direction. Return exactly one JSON object with this shape: {{"hypothesis_id":"mechanism_family|discovered_primitive","discovery_spec":{{...}},"conceptual_change":"...","evidence_sources":["..."],"rationale":"...","is_testable":true,"oos_selection_used":false}}. For mechanism_family, discovery_spec MUST contain mechanism_family, threshold and direction. For discovered_primitive, discovery_spec MUST contain mechanism_family, operator, left, threshold and direction, plus right for difference/ratio and window for windowed operators. mechanism_family MUST equal SELECTED_SURVIVOR_FAMILY. Do not put discovery_spec fields at the top level. Do not use a family name as hypothesis_id unless it is exactly SELECTED_SURVIVOR_FAMILY. Return JSON only. When the surrounding harness exposes an asynchronous completion event, never use sleep/wait/status polling to wait for it; yield and resume on the event instead.'''
_PROVIDER_LAST_CALL=0.0
USAGE_PATH=ROOT/"research/provider_usage.json"
RPD_LIMIT=max(1,int(os.getenv("RESEARCH_PROVIDER_RPD_LIMIT","450")))
bc=parent=0;selected_family=""
def config():
 return "https://generativelanguage.googleapis.com/v1beta/openai/",os.getenv("GEMINI_MODEL","gemini-3.5-flash-lite"),os.getenv("GEMINI_API_KEY","")
def interval():
 try:return max(4.5,float(os.getenv("RESEARCH_PROVIDER_MIN_INTERVAL_SECONDS","5")))
 except ValueError:return 5.0
def compact(s,limit=None):
 limit=limit or max(4000,int(os.getenv("RESEARCH_PROVIDER_CONTEXT_CHAR_LIMIT","12000")));s=s or ""
 return s if len(s)<=limit else s[:limit//2]+f"\n...[compacted {len(s)-limit} chars]...\n"+s[-(limit-limit//2):]
def _reserve_rpd_slot():
 day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
 try: state=json.loads(USAGE_PATH.read_text(encoding="utf-8")) if USAGE_PATH.exists() else {}
 except Exception: state={}
 if state.get("day")!=day: state={"day":day,"calls":0}
 calls=int(state.get("calls",0))
 if calls>=RPD_LIMIT: raise RuntimeError(f"provider_rpd_budget_exhausted:{calls}/{RPD_LIMIT}")
 state["calls"]=calls+1; USAGE_PATH.write_text(json.dumps(state,sort_keys=True)+"\n",encoding="utf-8")
 return state["calls"]
def call(prompt):
 global _PROVIDER_LAST_CALL
 base,model,key=config()
 if not key:raise RuntimeError("provider_not_configured:GEMINI")
 _reserve_rpd_slot()
 gap=interval()-(time.monotonic()-_PROVIDER_LAST_CALL)
 if gap>0:time.sleep(gap)
 body={"model":model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"max_tokens":700,"response_format":{"type":"json_object"}}
 req=urllib.request.Request(base.rstrip("/")+"/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"},method="POST")
 _PROVIDER_LAST_CALL=time.monotonic();retries=max(0,int(os.getenv("RESEARCH_PROVIDER_RATE_RETRIES","3")))
 for attempt in range(retries+1):
  try:
   with urllib.request.urlopen(req,timeout=90) as r:return json.loads(r.read().decode())["choices"][0]["message"]["content"]
  except urllib.error.HTTPError as e:
   if e.code not in {429,500,502,503,504}:raise
   if attempt>=retries:raise RuntimeError(f"provider_{'rate_limited' if e.code==429 else 'http_'+str(e.code)}:GEMINI") from e
   time.sleep(min(float(os.getenv("RESEARCH_PROVIDER_BACKOFF_CAP_SECONDS","120")),15.0*(2**attempt)+random.uniform(0,3)));_PROVIDER_LAST_CALL=time.monotonic()
 raise RuntimeError("provider_request_failed:GEMINI")
def normalize_structural_types(c):
 s=c.get("discovery_spec")
 if not isinstance(s,dict):return
 if "threshold" not in s and "numeric_finite_threshold" in s:
  v=s.get("numeric_finite_threshold")
  try:v=float(v)
  except (TypeError,ValueError):return
  if math.isfinite(v):s["threshold"]=int(v) if v.is_integer() else v
 if isinstance(s.get("threshold"),str):
  try:v=float(s["threshold"])
  except ValueError:return
  if math.isfinite(v):s["threshold"]=int(v) if v.is_integer() else v
 if isinstance(s.get("window"),str) and s["window"].strip().isdigit():s["window"]=int(s["window"].strip())
def normalize_hypothesis_id(c):
 spec=c.get("discovery_spec")
 structural_fields={"mechanism_family","operator","left","right","window","threshold","direction","numeric_finite_threshold"}
 if not isinstance(spec,dict):
  spec={k:c.pop(k) for k in list(c) if k in structural_fields}
  if spec:c["discovery_spec"]=spec
  else:return
 else:
  for key in structural_fields:
   if key not in spec and key in c: spec[key]=c.pop(key)
 explicit_family=spec.get("mechanism_family")
 if explicit_family is not None:
  if explicit_family==selected_family:c["hypothesis_id"]="mechanism_family"
  return
 if c.get("hypothesis_id")==selected_family:
  c["hypothesis_id"]="mechanism_family";spec["mechanism_family"]=selected_family;return
 primitive_shape=(spec.get("mechanism_family")==selected_family and spec.get("operator") in OPERATORS and spec.get("left") in COLUMNS)
 if c.get("hypothesis_id") not in {"mechanism_family","discovered_primitive"} and primitive_shape:c["hypothesis_id"]="discovered_primitive"
def fingerprint(c):return structural_key(c)
def prior_fingerprints():
 out=set();d=ROOT/"research/autonomous_candidates"
 if not d.exists():return out
 for p in sorted(d.glob("BC*.json")):
  try:
   f=fingerprint(json.loads(p.read_text(encoding="utf-8")))
   if f is not None:out.add(f)
  except Exception:pass
 return out
def deterministic_candidate(forbidden):
 profile=FAMILY_PRIMITIVES.get(selected_family)
 if not profile:raise ValueError("deterministic_translation_family_profile_missing")
 thresholds=(0.0,0.5,1.0);windows=(3,5,10,20,50,100)
 preferred={"smc_ict":[("difference","high","low"),("delta","close",None),("lag","close",None),("difference","close","low"),("difference","high","close")],"fvg_imbalance":[("difference","high","low"),("delta","close",None),("difference","close","low"),("difference","high","close")],"wyckoff_vsa_vpa":[("ratio","volume","range_ratio"),("difference","close","open"),("difference","high","low"),("delta","volume",None)],"vwap_volume_profile":[("difference","close","vwap_distance"),("zscore","vwap_distance",None),("ratio","volume","volume_ratio")]}
 specs=[]
 for op,left,right in preferred.get(selected_family,[]):
  if op in profile["ops"] and left in profile["cols"] and (right is None or right in profile["cols"]):specs.append((op,left,right))
 for op in sorted(profile["ops"]):
  for left in sorted(profile["cols"]):
   for right in (sorted(profile["cols"]) if op in {"difference","ratio"} else (None,)):specs.append((op,left,right))
 seen=set()
 for op,left,right in specs:
  if (op,left,right) in seen:continue
  seen.add((op,left,right));ws=windows if op in {"zscore","rolling_mean","rolling_std","lag","delta","rank"} else (None,)
  for window in ws:
   for direction in ("above","below"):
    for threshold in thresholds:
     spec={"mechanism_family":selected_family,"operator":op,"left":left,"direction":direction,"threshold":threshold}
     if right is not None:spec["right"]=right
     if window is not None:spec["window"]=window
     candidate={"bc":bc,"parent_bc":parent,"hypothesis_id":"discovered_primitive","discovery_spec":spec,"conceptual_change":f"BTC-compatible {selected_family} proxy using {op}({left})"+(f" with {right}" if right else "")+(f" over window {window}" if window else ""),"evidence_sources":[],"rationale":"","is_testable":True,"oos_selection_used":False}
     if fingerprint(candidate) in forbidden:continue
     ok,reason=validate_candidate(candidate,bc,parent)
     if ok:return candidate
 raise ValueError("deterministic_translation_frontier_exhausted")
def request_candidate(prompt,forbidden):
 feedback="";last="unknown"
 for _ in range(3):
  try:c=json.loads(call(prompt+feedback))
  except RuntimeError as e:
   last=str(e)
   if "provider_rate_limited" in last:
    print("PROVIDER_FALLBACK_DETERMINISTIC reason=provider_rate_limited");return deterministic_candidate(forbidden)
   raise
  except json.JSONDecodeError:last="invalid_json";feedback="\nVALIDATOR_FEEDBACK: invalid JSON; return one JSON object matching the required schema.\n";continue
  if not isinstance(c,dict):last="invalid_json_shape";feedback="\nVALIDATOR_FEEDBACK: top-level JSON must be exactly one object.\n";continue
  if c.get("status")=="HOLD":return c
  normalize_structural_types(c);normalize_hypothesis_id(c);hid=c.get("hypothesis_id");spec=c.get("discovery_spec")
  if hid not in {"discovered_primitive","mechanism_family"}:reason="translation_hypothesis_id_forbidden"
  elif hid=="mechanism_family" and (not isinstance(spec,dict) or spec.get("mechanism_family")!=selected_family):reason="selected_family_mismatch"
  else:
   c["bc"],c["parent_bc"]=bc,parent;f=fingerprint(c)
   if f in forbidden:reason="duplicate_structural_mechanism"
   else:
    ok,reason=validate_candidate(c,bc,parent)
    if ok:return c
  last=reason
  if reason=="duplicate_structural_mechanism":feedback="\nVALIDATOR_FEEDBACK: duplicate_structural_mechanism. DUPLICATE structural key rejected. Choose a genuinely different executable structural mechanism; threshold/window alone is not novelty. If none exists, return HOLD.\n"
  else:feedback=f"\nVALIDATOR_FEEDBACK: {reason}. Return the exact required JSON schema and choose a genuinely different executable structural mechanism; threshold/window alone is not novelty. If none exists, return HOLD.\n"
 print(f"PROVIDER_FALLBACK_DETERMINISTIC reason=provider_candidate_contract_failed:{last}");return deterministic_candidate(forbidden)
def ground_candidate(c,selected):
 family=str(selected.get("family") or "").strip();url=str(selected.get("source_url") or "").strip()
 if not url:raise ValueError("selected_survivor_missing_source_url")
 if family not in EXECUTABLE_MECHANISM_FAMILIES:raise ValueError(f"non_executable_source_reached_grounding:{family}")
 if c.get("hypothesis_id")=="mechanism_family":
  if not isinstance(c.get("discovery_spec"),dict) or c["discovery_spec"].get("mechanism_family")!=family:raise ValueError("selected_family_mismatch")
 elif c.get("hypothesis_id")!="discovered_primitive":raise ValueError("translation_hypothesis_id_forbidden")
 else:
  spec=c.get("discovery_spec")
  if not isinstance(spec,dict):raise ValueError("discovery_spec_required")
  spec["mechanism_family"]=family
 c.pop("candidate_hash",None);c["evidence_sources"]=[url];c["rationale"]="Executable BTC translation of the selected portable mechanism; proposed test only.";c["is_testable"]=True;c["oos_selection_used"]=False;c.update(novelty_metadata(c));return c
def survivor_evidence(s):return compact(json.dumps({k:s.get(k) for k in ("candidate_id","source","source_url","title","description","family","market","query","source_timestamp","lineage")},sort_keys=True,ensure_ascii=False,separators=(",",":")))
def main():
 global bc,parent,selected_family
 failure=Path(os.environ["RESEARCH_FAILURE_ANALYSIS"]);out=Path(os.environ["RESEARCH_CANDIDATE_OUTPUT"]);bc=int(os.environ["RESEARCH_NEXT_BC"]);parent=int(os.environ["RESEARCH_PARENT_BC"]);queue=ROOT/"research/discovery/research_queue.json"
 if not queue.exists():print("PROVIDER_ROUTER_HOLD missing_screen_queue");return 0
 try:
  q=json.loads(queue.read_text(encoding="utf-8"));raw=q.get("candidates",[]) if isinstance(q,dict) else q;survivors=[s for s in raw if isinstance(s,dict) and str(s.get("source_url") or "").strip()];eligible,_=eligible_survivors(survivors);eligible=[s for s in eligible if str(s.get("family") or "").strip() in EXECUTABLE_MECHANISM_FAMILIES]
  if not eligible:print("PROVIDER_ROUTER_HOLD no_executable_btc_compatible_screen_survivor");return 0
  families=[]
  for s in eligible:
   f=str(s.get("family") or "").strip()
   if f and f not in families:families.append(f)
  ranked=rank_families(families,seed=bc);selected_family=ranked[0];selected=next(s for s in eligible if str(s.get("family") or "").strip()==selected_family);note_selection(selected_family,bc)
 except Exception as e:print(f"PROVIDER_ROUTER_HOLD malformed_screen_queue:{e}");return 0
 forbidden=prior_fingerprints();failure_text=compact(failure.read_text(encoding="utf-8"));payload=json.dumps([list(x) for x in sorted(forbidden,key=str)],separators=(",",":"));prompt=f"Parent BC: {parent}\nNext BC: {bc}\nTARGET_MARKET: BTCUSDT\nTARGET_TIMEFRAME: 1H\nSELECTED_SURVIVOR_FAMILY: {json.dumps(selected_family)}\nFORBIDDEN_STRUCTURAL_MECHANISMS_COMPLETE: {payload}\nFAILURE ANALYSIS (repair context only):\n{failure_text}\nSELECTED SCREEN SURVIVOR (authoritative):\n{json.dumps(selected,sort_keys=True,separators=(",",":"))}\nTranslate faithfully; if no genuinely different OHLCV expression is supported, return HOLD."
 try:
  c=request_candidate(prompt,forbidden)
  if c.get("status")=="HOLD":print("PROVIDER_GEMINI_HOLD");return 0
  ground_candidate(c,selected);ok,reason=validate_candidate(c,bc,parent)
  if not ok:raise ValueError(f"grounded_candidate_contract_failed:{reason}")
  base,model,key=config();calibrated,issues=verify_with_openai_compatible(base,model,key,c,survivor_evidence(selected))
  if not calibrated:raise ValueError("PROVIDER_CALIBRATION_FAIL "+json.dumps(issues,sort_keys=True))
  write_candidate(out,c);print(f"PROVIDER_SELECTED GEMINI model={model} family={selected_family} novelty={c['novelty_key']} hash={c['candidate_hash']}");return 0
 except Exception as e:print(f"PROVIDER_FAIL GEMINI: {e}")
 print("PROVIDER_ROUTER_HOLD");return 0
if __name__=="__main__":raise SystemExit(main())
