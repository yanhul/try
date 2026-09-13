#!/usr/bin/env python3
"""Strict single-Gemini translation boundary for one BTC-compatible screen survivor."""
from __future__ import annotations
import json,math,os,random,sys,time,urllib.error,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.autonomous_hypothesis import write_candidate,validate_candidate,MECHANISM_FAMILIES
from research.evidence_calibration import verify_with_openai_compatible
from research.btc_translation_policy import eligible_survivors

OPERATORS=["identity","difference","ratio","zscore","rolling_mean","rolling_std","lag","delta","rank"]
COLUMNS=["open","high","low","close","volume","volume_ratio","range_ratio","close_location","vwap_distance"]
WINDOWS=[3,5,10,20,50,100]
SYSTEM=f'''You translate ONLY the SELECTED BTC-COMPATIBLE SCREEN SURVIVOR supplied by the controller. You are not a selector. Never replace the survivor. Use only BTCUSDT 1H OHLCV data. Never use OOS, expected performance, stars or intuition as evidence. The only valid mechanism_family labels are {sorted(MECHANISM_FAMILIES)}. If hypothesis_id="mechanism_family", discovery_spec.mechanism_family MUST be exactly SELECTED_SURVIVOR_FAMILY; never invent, rename, generalize, or substitute a family label. If the selected family is not faithfully executable as a mechanism family, output hypothesis_id="discovered_primitive" only when an executable OHLCV translation is genuinely supported; NEVER convert an incompatible source into a generic primitive. For discovered_primitive use only operators {OPERATORS}, columns {COLUMNS}, windows {WINDOWS}. discovery_spec uses the key threshold (not numeric_finite_threshold), and requires operator,left,numeric finite threshold,direction above/below; difference/ratio also require right from exactly {COLUMNS}. Threshold is a test parameter, never evidence. Return JSON only with keys hypothesis_id,conceptual_change,evidence_sources,rationale,is_testable,oos_selection_used,discovery_spec.'''
_PROVIDER_LAST_CALL=0.0
bc=0;parent=0;selected_family=""

def config():
 base="https://generativelanguage.googleapis.com/v1beta/openai/".rstrip("/")
 return base,os.getenv("GEMINI_MODEL","gemini-3.1-flash-lite"),os.getenv("GEMINI_API_KEY","")

def interval():
 try:return max(4.5,float(os.getenv("RESEARCH_PROVIDER_MIN_INTERVAL_SECONDS","5")))
 except ValueError:return 5.0

def compact(s,limit=None):
 limit=limit or max(4000,int(os.getenv("RESEARCH_PROVIDER_CONTEXT_CHAR_LIMIT","12000")));s=s or ""
 if len(s)<=limit:return s
 h=limit//2;return s[:h]+f"\n...[compacted {len(s)-limit} chars]...\n"+s[-(limit-h):]

def call(prompt):
 global _PROVIDER_LAST_CALL
 base,model,key=config()
 if not key:raise RuntimeError("provider_not_configured:GEMINI")
 gap=interval()-(time.monotonic()-_PROVIDER_LAST_CALL)
 if gap>0:time.sleep(gap)
 body={"model":model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"max_tokens":700,"response_format":{"type":"json_object"}}
 req=urllib.request.Request(base+"/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"},method="POST")
 _PROVIDER_LAST_CALL=time.monotonic();retries=max(0,int(os.getenv("RESEARCH_PROVIDER_RATE_RETRIES","1")))
 for attempt in range(retries+1):
  try:
   with urllib.request.urlopen(req,timeout=90) as r:return json.loads(r.read().decode())["choices"][0]["message"]["content"]
  except urllib.error.HTTPError as e:
   if e.code not in {429,500,502,503,504}:raise
   detail=""
   try:detail=e.read().decode("utf-8","replace")[:1000]
   except Exception:pass
   if attempt>=retries:raise RuntimeError(f"provider_{'rate_limited' if e.code==429 else 'http_'+str(e.code)}:GEMINI:{detail}") from e
   delay=min(float(os.getenv("RESEARCH_PROVIDER_BACKOFF_CAP_SECONDS","120")),2.0**attempt+random.uniform(0,1));print(f"PROVIDER_RATE_LIMIT name=GEMINI code={e.code} attempt={attempt+1}/{retries+1} backoff={delay:.1f}s",flush=True);time.sleep(delay);_PROVIDER_LAST_CALL=time.monotonic()
 raise RuntimeError("provider_request_failed:GEMINI")

def normalize_structural_types(c):
 s=c.get("discovery_spec")
 if not isinstance(s,dict):return
 if isinstance(s.get("threshold"),str):
  try:v=float(s["threshold"])
  except ValueError:return
  if math.isfinite(v):s["threshold"]=int(v) if v.is_integer() else v
 if isinstance(s.get("window"),str) and s["window"].strip().isdigit():s["window"]=int(s["window"].strip())

def fingerprint(c):
 s=c.get("discovery_spec") or {}
 return tuple(s.get(k) for k in ("mechanism_family","operator","left","right","window","threshold","direction")) if isinstance(s,dict) else None

def prior_fingerprints():
 out=set();d=ROOT/"research/autonomous_candidates"
 for p in sorted(d.glob("BC*.json")) if d.exists() else []:
  try:
   f=fingerprint(json.loads(p.read_text(encoding="utf-8")))
   if f is not None:out.add(f)
  except Exception:pass
 return out

def request_candidate(prompt,forbidden):
 feedback="";last="unknown"
 for _ in range(3):
  raw=call(prompt+feedback)
  try:c=json.loads(raw)
  except Exception:last="invalid_json";feedback="\nVALIDATOR_FEEDBACK: invalid JSON; return one JSON object.\n";continue
  if c.get("status")=="HOLD":return c
  normalize_structural_types(c);hid=c.get("hypothesis_id");spec=c.get("discovery_spec")
  if hid not in {"discovered_primitive","mechanism_family"}:reason="translation_hypothesis_id_forbidden"
  elif hid=="mechanism_family" and (not isinstance(spec,dict) or spec.get("mechanism_family")!=selected_family):reason="selected_family_mismatch"
  else:
   c["bc"],c["parent_bc"]=bc,parent;f=fingerprint(c)
   if f is not None and f in forbidden:reason="duplicate_discovery_fingerprint"
   else:
    ok,reason=validate_candidate(c,bc,parent)
    if ok:return c
  last=reason
  if reason=="selected_family_mismatch":feedback=f"\nVALIDATOR_FEEDBACK: mechanism_family is INVALID unless it exactly equals {selected_family!r}. Use hypothesis_id=mechanism_family with discovery_spec.mechanism_family={selected_family!r}, OR use discovered_primitive with a valid executable OHLCV spec. Do not invent any other family label.\n"
  elif reason=="duplicate_discovery_fingerprint":feedback="\nVALIDATOR_FEEDBACK: duplicate structural fingerprint. Regenerate a genuinely distinct executable proposal.\n"
  elif reason=="invalid_mechanism_family":feedback=f"\nVALIDATOR_FEEDBACK: invalid mechanism family. The ONLY allowed family for this request is {selected_family!r}; set discovery_spec.mechanism_family to that exact value if using mechanism_family.\n"
  else:feedback=f"\nVALIDATOR_FEEDBACK: {reason}. Regenerate only an executable BTC OHLCV translation.\n"
 raise ValueError(f"provider_candidate_contract_failed:{last}")

def ground_candidate(c,selected):
 url=str(selected.get("source_url") or "").strip();family=str(selected.get("family") or "").strip()
 if not url:raise ValueError("selected_survivor_missing_source_url")
 if family not in MECHANISM_FAMILIES:raise ValueError(f"non_executable_source_reached_grounding:{family}")
 if c.get("hypothesis_id")=="mechanism_family":
  spec=c.get("discovery_spec")
  if not isinstance(spec,dict) or spec.get("mechanism_family")!=family:raise ValueError("selected_family_mismatch")
 elif c.get("hypothesis_id")=="discovered_primitive":
  if not isinstance(c.get("discovery_spec"),dict):raise ValueError("discovery_spec_required")
 else:raise ValueError("translation_hypothesis_id_forbidden")
 c.pop("candidate_hash",None);c["evidence_sources"]=[url];c["rationale"]="Executable BTC translation of the selected portable mechanism; this is a proposed test and does not assert efficacy, causality, or performance.";c["is_testable"]=True;c["oos_selection_used"]=False
 return c

def survivor_evidence(s):
 return compact(json.dumps({k:s.get(k) for k in ("candidate_id","source","source_url","title","description","family","market","query","source_timestamp","lineage")},sort_keys=True,ensure_ascii=False,separators=(",",":")))

def main():
 global bc,parent,selected_family
 failure=Path(os.environ["RESEARCH_FAILURE_ANALYSIS"]);out=Path(os.environ["RESEARCH_CANDIDATE_OUTPUT"]);bc=int(os.environ["RESEARCH_NEXT_BC"]);parent=int(os.environ["RESEARCH_PARENT_BC"]);queue=ROOT/"research/discovery/research_queue.json"
 if not queue.exists():print("PROVIDER_ROUTER_HOLD missing_screen_queue");return 0
 try:
  q=json.loads(queue.read_text(encoding="utf-8"));raw=q.get("candidates",[]) if isinstance(q,dict) else q
  survivors=[s for s in raw if isinstance(s,dict) and str(s.get("source_url") or "").strip()]
  eligible,rejected=eligible_survivors(survivors)
  non_executable=[s for s in eligible if str(s.get("family") or "").strip() not in MECHANISM_FAMILIES]
  eligible=[s for s in eligible if str(s.get("family") or "").strip() in MECHANISM_FAMILIES]
  rejected=list(rejected)+[
   {"candidate_id":s.get("candidate_id"),"btc_translation_reason":"non_executable_source_family","family":s.get("family")}
   for s in non_executable
  ]
  if rejected:print("BTC_TRANSLATION_FILTER_REJECTED "+json.dumps({"count":len(rejected),"reasons":sorted({r.get("btc_translation_reason") for r in rejected})},sort_keys=True),flush=True)
  if not eligible:print("PROVIDER_ROUTER_HOLD no_executable_btc_compatible_screen_survivor");return 0
  families=[]
  for s in eligible:
   f=str(s.get("family") or "").strip()
   if f and f not in families:families.append(f)
  family=families[(parent-1)%len(families)]
  selected=next(s for s in eligible if str(s.get("family") or "").strip()==family);selected_family=family
 except Exception as e:print(f"PROVIDER_ROUTER_HOLD malformed_screen_queue:{e}");return 0
 forbidden=prior_fingerprints();failure_text=compact(failure.read_text(encoding="utf-8"));evidence=survivor_evidence(selected)
 prompt=(f"Parent BC: {parent}\nNext BC: {bc}\nTARGET_MARKET: BTCUSDT\nTARGET_TIMEFRAME: 1H\nSELECTED_SURVIVOR_FAMILY: {json.dumps(selected_family)}\nALLOWED_MECHANISM_FAMILY_FOR_THIS_REQUEST: {json.dumps(selected_family)}\nFORBIDDEN_DISCOVERY_FINGERPRINTS: {json.dumps([list(x) for x in sorted(forbidden,key=str)[-80:]],separators=(',',':'))}\nFAILURE ANALYSIS (repair context only, never evidence):\n{failure_text}\nSELECTED SCREEN SURVIVOR (authoritative; translate this one only):\n{json.dumps(selected,sort_keys=True,separators=(',',':'))}\nTranslate the mechanism faithfully to BTCUSDT 1H without changing asset, data lane, or selected family. If you use hypothesis_id=mechanism_family, discovery_spec.mechanism_family MUST equal the exact selected family above.")
 try:
  c=request_candidate(prompt,forbidden)
  if c.get("status")=="HOLD":print("PROVIDER_GEMINI_HOLD");return 0
  ground_candidate(c,selected);ok,reason=validate_candidate(c,bc,parent)
  if not ok:raise ValueError(f"grounded_candidate_contract_failed:{reason}")
  base,model,key=config();calibrated,issues=verify_with_openai_compatible(base,model,key,c,evidence)
  if not calibrated:raise ValueError("PROVIDER_CALIBRATION_FAIL "+json.dumps(issues,sort_keys=True))
  write_candidate(out,c);print(f"PROVIDER_SELECTED GEMINI model={model} family={selected_family} hash={c['candidate_hash']}");return 0
 except Exception as e:
  print(f"PROVIDER_FAIL GEMINI: {e}")
 print("PROVIDER_ROUTER_HOLD");return 0

if __name__=="__main__":raise SystemExit(main())
