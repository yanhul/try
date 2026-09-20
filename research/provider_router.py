#!/usr/bin/env python3
from __future__ import annotations
import json,math,os,random,sys,time,urllib.error,urllib.request
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
SYSTEM=f'''Translate ONLY the SELECTED BTC-COMPATIBLE SCREEN SURVIVOR. You are not a selector. Use only BTCUSDT 1H OHLCV. Never use OOS, expected performance, stars or intuition as evidence. Valid families: {sorted(MECHANISM_FAMILIES)}. A mechanism_family hypothesis MUST use exactly SELECTED_SURVIVOR_FAMILY. discovered_primitive may use only operators {OPERATORS} and columns {COLUMNS}. Threshold/window are parameters, NOT novelty. New hypotheses must change family/operator/left/right/direction. Return exactly one JSON object with this shape: {{"hypothesis_id":"mechanism_family|discovered_primitive","discovery_spec":{{...}},"conceptual_change":"...","evidence_sources":["..."],"rationale":"...","is_testable":true,"oos_selection_used":false}}. For mechanism_family, discovery_spec MUST contain mechanism_family, threshold and direction. For discovered_primitive, discovery_spec MUST contain mechanism_family, operator, left, threshold and direction, plus right for difference/ratio and window for windowed operators. mechanism_family MUST equal SELECTED_SURVIVOR_FAMILY. Do not put discovery_spec fields at the top level. Do not use a family name as hypothesis_id unless it is exactly SELECTED_SURVIVOR_FAMILY. Return JSON only.'''
_PROVIDER_LAST_CALL=0.0
bc=parent=0;selected_family=""
def config(): return "https://generativelanguage.googleapis.com/v1beta/openai/",os.getenv("GEMINI_MODEL","gemini-3.5-flash-lite"),os.getenv("GEMINI_API_KEY","")
def interval():
 try:return max(4.5,float(os.getenv("RESEARCH_PROVIDER_MIN_INTERVAL_SECONDS","5")))
 except ValueError:return 5.0
def compact(s,limit=None):
 limit=limit or max(4000,int(os.getenv("RESEARCH_PROVIDER_CONTEXT_CHAR_LIMIT","12000")));s=s or ""
 return s if len(s)<=limit else s[:limit//2]+f"\n...[compacted {len(s)-limit} chars]...\n"+s[-(limit-limit//2):]
def call(prompt):
 global _PROVIDER_LAST_CALL
 base,model,key=config()
 if not key:raise RuntimeError("provider_not_configured:GEMINI")
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
    """Canonicalize provider metadata while preserving executable semantics."""
    spec=c.get("discovery_spec")
    structural_fields={"mechanism_family","operator","left","right","window","threshold","direction","numeric_finite_threshold"}
    if not isinstance(spec,dict):
        spec={k:c.pop(k) for k in list(c) if k in structural_fields}
        if spec:c["discovery_spec"]=spec
        else:return
    else:
        # Repair the common provider serialization mistake without inventing values.
        for key in structural_fields:
            if key not in spec and key in c: spec[key]=c.pop(key)
    explicit_family=spec.get("mechanism_family")
    if explicit_family is not None:
        if explicit_family==selected_family:
            c["hypothesis_id"]="mechanism_family"
        return
    if c.get("hypothesis_id")==selected_family:
        c["hypothesis_id"]="mechanism_family"
        spec["mechanism_family"]=selected_family
        return
    primitive_shape=(spec.get("mechanism_family") == selected_family and spec.get("operator") in OPERATORS and spec.get("left") in COLUMNS)
    if c.get("hypothesis_id") not in {"mechanism_family","discovered_primitive"} and primitive_shape:
        c["hypothesis_id"]="discovered_primitive"
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
    """Generate the next admissible family-specific proxy without broad cartesian enumeration."""
    profile=FAMILY_PRIMITIVES.get(selected_family)
    if not profile:
        raise ValueError("deterministic_translation_family_profile_missing")
    thresholds=(0.0,0.5,1.0)
    windows=(3,5,10,20,50,100)
    # Prefer semantically compact proxies before widening the local frontier.
    preferred={
        "smc_ict":[("difference","high","low"),("delta","close",None),("lag","close",None),("difference","close","low"),("difference","high","close")],
        "fvg_imbalance":[("difference","high","low"),("delta","close",None),("difference","close","low"),("difference","high","close")],
        "wyckoff_vsa_vpa":[("ratio","volume","range_ratio"),("difference","close","open"),("difference","high","low"),("delta","volume",None)],
        "vwap_volume_profile":[("difference","close","vwap_distance"),("zscore","vwap_distance",None),("ratio","volume","volume_ratio")],
    }
    specs=[]
    for op,left,right in preferred.get(selected_family,[]):
        if op not in profile["ops"] or left not in profile["cols"] or (right is not None and right not in profile["cols"]): continue
        specs.append((op,left,right))
    for op in sorted(profile["ops"]):
        for left in sorted(profile["cols"]):
            rights=sorted(profile["cols"]) if op in {"difference","ratio"} else (None,)
            for right in rights: specs.append((op,left,right))
    seen=set()
    for op,left,right in specs:
        key0=(op,left,right)
        if key0 in seen: continue
        seen.add(key0)
        ws=windows if op in {"zscore","rolling_mean","rolling_std","lag","delta","rank"} else (None,)
        for window in ws:
            for direction in ("above","below"):
                for threshold in thresholds:
                    spec={"mechanism_family":selected_family,"operator":op,"left":left,"direction":direction,"threshold":threshold}
                    if right is not None: spec["right"]=right
                    if window is not None: spec["window"]=window
                    candidate={"bc":bc,"parent_bc":parent,"hypothesis_id":"discovered_primitive",
                      "discovery_spec":spec,
                      "conceptual_change":f"BTC-compatible {selected_family} proxy using {op}({left})" + (f" with {right}" if right else "") + (f" over window {window}" if window else ""),
                      "evidence_sources":[],"rationale":"","is_testable":True,"oos_selection_used":False}
                    key=fingerprint(candidate)
                    if key in forbidden: continue
                    ok,reason=validate_candidate(candidate,bc,parent)
                    if ok:return candidate
    raise ValueError("deterministic_translation_frontier_exhausted")
)