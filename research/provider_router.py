#!/usr/bin/env python3
"""Strict Gemini translation boundary for one deterministic screen survivor."""
from __future__ import annotations
import json,math,os,random,sys,time,urllib.error,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research.autonomous_hypothesis import write_candidate,validate_candidate,MECHANISM_FAMILIES
from engine.hypotheses import HYPOTHESES
from research.evidence_calibration import verify_with_openai_compatible
OPERATORS=["identity","difference","ratio","zscore","rolling_mean","rolling_std","lag","delta","rank"]
COLUMNS=["open","high","low","close","volume","volume_ratio","range_ratio","close_location","vwap_distance"]
WINDOWS=[3,5,10,20,50,100]
SYSTEM=f'''You translate ONLY the SELECTED SCREEN SURVIVOR supplied by the controller. You are not a selector. Never replace the survivor. Do not use OOS, expected performance, stars or intuition. Registered hypothesis_ids are allowed; otherwise use hypothesis_id="discovered_primitive". If the selected survivor family is one of the executable mechanism families, use hypothesis_id="mechanism_family" and discovery_spec.mechanism_family exactly as supplied by the survivor family. If the selected survivor family is NOT an executable mechanism family, NEVER use hypothesis_id="mechanism_family"; use hypothesis_id="discovered_primitive" with an executable discovery_spec. Mechanism families are {sorted(MECHANISM_FAMILIES)}. For mechanism_family use only numeric finite threshold (default 0) and direction above/below. For discovered_primitive use only operators {OPERATORS}, columns {COLUMNS}, windows {WINDOWS}. discovery_spec requires operator,left,numeric finite threshold,direction above/below; difference/ratio also require right from exactly {COLUMNS}. Threshold is a test parameter, never evidence. Do not invent evidence. Return JSON only with keys hypothesis_id,conceptual_change,evidence_sources,rationale,is_testable,oos_selection_used,discovery_spec.'''
_PROVIDER_LAST_CALL=0.0
bc=0
parent=0
selected_family=""
def config(name):
 n=name.upper();d={"GEMINI":("https://generativelanguage.googleapis.com/v1beta/openai/",os.getenv("GEMINI_MODEL","gemini-3.1-flash-lite"),"GEMINI_API_KEY"),"DEEPSEEK":("https://api.deepseek.com",os.getenv("DEEPSEEK_MODEL","deepseek-v4-flash"),"DEEPSEEK_API_KEY")}
 if n in d:b,m,k=d[n]
 else:b=os.getenv(f"RESEARCH_PROVIDER_{n}_BASE_URL","");m=os.getenv(f"RESEARCH_PROVIDER_{n}_MODEL","");k=f"RESEARCH_PROVIDER_{n}_API_KEY"
 return b.rstrip("/"),m,os.getenv(k,"")
def interval():
 try:return max(4.5,float(os.getenv("RESEARCH_PROVIDER_MIN_INTERVAL_SECONDS","4.5")))
 except ValueError:return 4.5
def compact(s,limit=None):
 limit=limit or max(4000,int(os.getenv("RESEARCH_PROVIDER_CONTEXT_CHAR_LIMIT","12000")));s=s or ""
 if len(s)<=limit:return s
 h=limit//2;return s[:h]+f"\n...[compacted {len(s)-limit} chars]...\n"+s[-(limit-h):]
def call(name,prompt):
 global _PROVIDER_LAST_CALL
 base,model,key=config(name)
 if not base or not model or not key:raise RuntimeError(f"provider_not_configured:{name}")
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
   if attempt>=retries:raise RuntimeError(f"provider_{'rate_limited' if e.code==429 else 'http_'+str(e.code)}:{name}:{detail}") from e
   delay=min(float(os.getenv("RESEARCH_PROVIDER_BACKOFF_CAP_SECONDS","120")),2.0**attempt+random.uniform(0,1));print(f"PROVIDER_RATE_LIMIT name={name} code={e.code} attempt={attempt+1}/{retries+1} backoff={delay:.1f}s detail={detail}",flush=True);time.sleep(delay);_PROVIDER_LAST_CALL=time.monotonic()
 raise RuntimeError(f"provider_request_failed:{name}")
def normalize_structural_types(c):
 s=c.get("discovery_spec")
 if not isinstance(s,dict):return
 if isinstance(s.get("threshold"),str):
  try:v=float(s["threshold"])
  except ValueError:return
  if math.isfinite(v):s["threshold"]=int(v) if v.is_integer() else v
 if isinstance(s.get("window"),str) and s["window"].strip().isdigit():s["window"]=int(s["window"].strip())
def fingerprint(c):
 s=c.get("discovery_spec") or {};return tuple(s.get(k) for k in ("mechanism_family","operator","left","right","window","threshold","direction")) if isinstance(s,dict) else None
def prior_fingerprints():
 out=set();d=ROOT/"research/autonomous_candidates"
 for p in sorted(d.glob("BC*.json")) if d.exists() else []:
  try:
   f=fingerprint(json.loads(p.read_text(encoding="utf-8")))
   if f is not None:out.add(f)
  except Exception:pass
 return out
def request_candidate(name,prompt,forbidden):
 feedback="";last="unknown"
 for _ in range(3):
  raw=call(name,prompt+feedback)
  try:c=json.loads(raw)
  except Exception:last="invalid_json";feedback="\nVALIDATOR_FEEDBACK: invalid JSON; return one JSON object.\n";continue
  if c.get("status")=="HOLD":return c
  normalize_structural_types(c);hid=c.get("hypothesis_id")
  if not isinstance(hid,str):reason="invalid_hypothesis_id_type"
  elif hid not in HYPOTHESES and hid not in {"discovered_primitive","mechanism_family"}:reason="unregistered_hypothesis_id"
  elif hid=="mechanism_family" and selected_family not in MECHANISM_FAMILIES:reason="unsupported_survivor_mechanism_family"
  else:
   c["bc"],c["parent_bc"]=bc,parent;f=fingerprint(c)
   if f is not None and f in forbidden:reason="duplicate_discovery_fingerprint"
   else:
    ok,reason=validate_candidate(c,bc,parent)
    if ok:return c
  last=reason;spec=c.get("discovery_spec") if isinstance(c,dict) else None
  if reason=="invalid_mechanism_family":feedback="\nVALIDATOR_FEEDBACK: invalid_mechanism_family. Use the exact executable survivor family from the selected screen survivor.\n"
  elif reason=="unsupported_survivor_mechanism_family":feedback="\nVALIDATOR_FEEDBACK: unsupported_survivor_mechanism_family. The selected survivor family is not an executable mechanism family. Do NOT use hypothesis_id=mechanism_family. Return hypothesis_id=discovered_primitive with a valid executable discovery_spec using the allowed operators/columns/windows.\n"
  elif reason=="invalid_discovery_threshold":
   if isinstance(spec,dict) and "threshold" not in spec:
    spec["threshold"]=0;ok,again=validate_candidate(c,bc,parent)
    if ok:return c
   feedback="\nVALIDATOR_FEEDBACK: invalid_discovery_threshold. Output a plain finite JSON NUMBER threshold and direction exactly 'above' or 'below'. If no threshold is determined by the survivor, use threshold 0.\n"
  elif reason=="invalid_discovery_right_column":
   bad=spec.get("right") if isinstance(spec,dict) else None;feedback="\nVALIDATOR_FEEDBACK: invalid_discovery_right_column. For difference/ratio, right must be exactly one of "+json.dumps(COLUMNS)+"; aliases and prose are forbidden. Received "+json.dumps(bad)+".\n"
  elif reason=="invalid_discovery_window":feedback="\nVALIDATOR_FEEDBACK: invalid_discovery_window. Use exactly one integer window from "+json.dumps(WINDOWS)+".\n"
  elif reason=="invalid_discovery_operator":feedback="\nVALIDATOR_FEEDBACK: invalid_discovery_operator. Use exactly one operator from "+json.dumps(OPERATORS)+".\n"
  elif reason=="invalid_discovery_left_column":feedback="\nVALIDATOR_FEEDBACK: invalid_discovery_left_column. Use exactly one schema column from "+json.dumps(COLUMNS)+".\n"
  elif reason=="duplicate_discovery_fingerprint":feedback="\nVALIDATOR_FEEDBACK: duplicate_discovery_fingerprint. Regenerate a genuinely distinct executable discovery_spec.\n"
  else:feedback=f"\nVALIDATOR_FEEDBACK: {reason}. Regenerate only the executable proposal; do not invent evidence.\n"
 raise ValueError(f"provider_candidate_contract_failed:{last}")
def ground_candidate(c,selected):
 url=str(selected.get("source_url") or "").strip()
 if not url:raise ValueError("selected_survivor_missing_source_url")
 c.pop("candidate_hash",None);family=str(selected.get("family") or "").strip()
 if family in MECHANISM_FAMILIES:
  c["hypothesis_id"]="mechanism_family";c["discovery_spec"]={"mechanism_family":family,"threshold":0,"direction":"above"};expr=f"mechanism_family({family})"
 else:
  if c.get("hypothesis_id")=="mechanism_family":
   raise ValueError("unsupported_survivor_family_reached_grounding")
  s=c.get("discovery_spec") or {};op=s.get("operator") if isinstance(s,dict) else None;expr=f"{op}({s.get('left')}"+(f",{s.get('right')})" if s.get('right') is not None else ")") if op else str(c.get("hypothesis_id"))
 c["evidence_sources"]=[url];c["conceptual_change"]=f"Test {expr} as the executable translation of the selected screen survivor.";c["rationale"]="This is a proposed executable test; it does not assert efficacy, causality, market behavior, or performance.";c["is_testable"]=True;c["oos_selection_used"]=False
 return c
def survivor_evidence(s):
 return compact(json.dumps({k:s.get(k) for k in ("candidate_id","source","source_url","title","description","family","market","query","source_timestamp","lineage")},sort_keys=True,ensure_ascii=False,separators=(",",":")))
def main():
 global bc,parent,selected_family
 failure=Path(os.environ["RESEARCH_FAILURE_ANALYSIS"]);out=Path(os.environ["RESEARCH_CANDIDATE_OUTPUT"]);bc=int(os.environ["RESEARCH_NEXT_BC"]);parent=int(os.environ["RESEARCH_PARENT_BC"]);queue=ROOT/"research/discovery/research_queue.json"
 if not queue.exists():print("PROVIDER_ROUTER_HOLD missing_screen_queue");return 0
 try:
  q=json.loads(queue.read_text(encoding="utf-8"));raw_survivors=q.get("candidates",[]) if isinstance(q,dict) else q;survivors=[s for s in raw_survivors if isinstance(s,dict) and str(s.get("source_url") or "").strip()]
  if not survivors:print("PROVIDER_ROUTER_HOLD no_screen_survivor_with_provenance");return 0
  selected=survivors[(parent-1)%len(survivors)];selected_family=str(selected.get("family") or "").strip()
 except Exception as e:print(f"PROVIDER_ROUTER_HOLD malformed_screen_queue:{e}");return 0
 forbidden=prior_fingerprints();failure_text=compact(failure.read_text(encoding="utf-8"));evidence=survivor_evidence(selected)
 prompt=(f"Parent BC: {parent}\nNext BC: {bc}\nSELECTED_SURVIVOR_FAMILY: {json.dumps(selected.get('family'))}\nREGISTERED_HYPOTHESES: {json.dumps(sorted(HYPOTHESES))}\nPRIOR_HYPOTHESIS_IDS: {compact(os.getenv('RESEARCH_PRIOR_HYPOTHESES','') or os.getenv('RESEARCH_USED_HYPOTHESIS_IDS',''),4000)}\nFORBIDDEN_DISCOVERY_FINGERPRINTS: {json.dumps([list(x) for x in sorted(forbidden,key=str)[-80:]],separators=(',',':'))}\nFAILURE ANALYSIS (repair context only, never evidence):\n{failure_text}\nSELECTED SCREEN SURVIVOR (authoritative; translate this one only):\n{json.dumps(selected,sort_keys=True,separators=(',',':'))}\nDo not add empirical claims to rationale; provenance and policy fields are grounded deterministically after translation.")
 for name in [x.strip().lower() for x in os.getenv("RESEARCH_PROVIDER_ORDER","gemini").split(",") if x.strip()]:
  try:
   c=request_candidate(name,prompt,forbidden)
   if c.get("status")=="HOLD":print(f"PROVIDER_{name.upper()}_HOLD");continue
   base,model,key=config(name)
   for attempt in range(3):
    ground_candidate(c,selected);ok,reason=validate_candidate(c,bc,parent)
    if not ok:raise ValueError(f"grounded_candidate_contract_failed:{reason}")
    time.sleep(interval());calibrated,issues=verify_with_openai_compatible(base,model,key,c,evidence)
    if calibrated:write_candidate(out,c);print(f"PROVIDER_SELECTED {name} model={model} hash={c['candidate_hash']} calibration_attempt={attempt+1}");return 0
    print(f"PROVIDER_CALIBRATION_FAIL {name} attempt={attempt+1} issues={json.dumps(issues,sort_keys=True)}",flush=True)
    if attempt==2:break
    revision=prompt+"\nCALIBRATION REJECTED; revise executable parameters only:\n"+json.dumps(issues,sort_keys=True);rf=set(forbidden);f=fingerprint(c)
    if f is not None:rf.add(f)
    c=request_candidate(name,revision,rf)
    if c.get("status")=="HOLD":break
  except Exception as e:print(f"PROVIDER_FAIL {name}: {e}")
 print("PROVIDER_ROUTER_HOLD");return 0
if __name__=="__main__":raise SystemExit(main())
