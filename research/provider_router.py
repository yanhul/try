#!/usr/bin/env python3
"""Strict provider router: discovery informs proposals; validation remains authoritative."""
from __future__ import annotations
import json, os, sys, time, urllib.error, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from autonomous_hypothesis import write_candidate, validate_candidate
from engine.hypotheses import HYPOTHESES
from evidence_calibration import verify_with_openai_compatible

OPERATORS=["identity","difference","ratio","zscore","rolling_mean","rolling_std","lag","delta","rank"]
COLUMNS=["open","high","low","close","volume","volume_ratio","range_ratio","close_location","vwap_distance"]
WINDOWS=[3,5,10,20,50,100]
SYSTEM=f"""You are an autonomous trading-research hypothesis generator.
Generate exactly ONE next executable hypothesis from FAILURE ANALYSIS plus BROAD DISCOVERY.
Registered hypothesis_ids are allowed; otherwise use hypothesis_id='discovered_primitive'.
For discovered_primitive, use ONLY operators {OPERATORS}, columns {COLUMNS}, windows {WINDOWS}.
A discovery_spec MUST contain operator,left, numeric threshold, direction ('above'/'below'); difference/ratio also require right; windowed operators require window.
Threshold and direction are a proposal to be tested, NOT evidence and NOT proof. Do not use OOS to select or tune.
Do not invent evidence. Exactly one conceptual change. Return JSON only with keys:
hypothesis_id,conceptual_change,evidence_sources,rationale,is_testable,oos_selection_used,discovery_spec.
"""

def config(name):
 n=name.upper(); defaults={"GEMINI":("https://generativelanguage.googleapis.com/v1beta/openai/",os.getenv("GEMINI_MODEL","gemini-3.1-flash-lite"),"GEMINI_API_KEY"),"DEEPSEEK":("https://api.deepseek.com",os.getenv("DEEPSEEK_MODEL","deepseek-v4-flash"),"DEEPSEEK_API_KEY")}
 if n in defaults: base,model,keyvar=defaults[n]
 else: base=os.getenv(f"RESEARCH_PROVIDER_{n}_BASE_URL",""); model=os.getenv(f"RESEARCH_PROVIDER_{n}_MODEL",""); keyvar=f"RESEARCH_PROVIDER_{n}_API_KEY"
 return base.rstrip("/"),model,os.getenv(keyvar,"")

def call(name,prompt):
 base,model,key=config(name)
 if not base or not model or not key: raise RuntimeError(f"provider_not_configured:{name}")
 body={"model":model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"max_tokens":1400,"response_format":{"type":"json_object"}}
 req=urllib.request.Request(base+"/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"},method="POST")
 last=None
 for attempt in range(3):
  try:
   with urllib.request.urlopen(req,timeout=90) as r:return json.loads(r.read().decode())["choices"][0]["message"]["content"]
  except urllib.error.HTTPError as exc:
   last=exc
   if exc.code not in {429,500,502,503,504} or attempt == 2: raise
   retry_after=exc.headers.get("Retry-After") if exc.headers else None
   try: delay=max(1,int(float(retry_after))) if retry_after else 2 ** attempt
   except ValueError: delay=2 ** attempt
   time.sleep(min(delay,15))
 if last: raise last
 raise RuntimeError(f"provider_request_failed:{name}")

def request_candidate(name,prompt):
 """Bounded structural repair: ask the same provider to regenerate, never inventing fields locally."""
 feedback=""
 for attempt in range(3):
  raw=call(name,prompt + feedback)
  try:
   candidate=json.loads(raw)
  except Exception as exc:
   feedback=("\n\nVALIDATOR_FEEDBACK: response was not valid JSON. Regenerate exactly one JSON object using the required keys; do not add prose.\n")
   continue
  if candidate.get("status")=="HOLD": return candidate
  if candidate.get("hypothesis_id") not in HYPOTHESES and candidate.get("hypothesis_id")!="discovered_primitive":
   reason="unregistered_hypothesis_id"
  else:
   reason=None
   candidate["bc"],candidate["parent_bc"]=bc,parent
   ok,reason=validate_candidate(candidate,bc,parent)
   if ok:return candidate
  feedback=(f"\n\nVALIDATOR_FEEDBACK: {reason}. Regenerate the candidate with that contract error corrected. "
            "Do not invent missing evidence or silently change the research policy. Threshold must be a JSON number and direction exactly 'above' or 'below'.\n")
 raise ValueError(f"provider_candidate_contract_failed:{reason}")

def main():
 global bc,parent
 failure=Path(os.environ["RESEARCH_FAILURE_ANALYSIS"]); output=Path(os.environ["RESEARCH_CANDIDATE_OUTPUT"]); bc=int(os.environ["RESEARCH_NEXT_BC"]); parent=int(os.environ["RESEARCH_PARENT_BC"])
 prior=os.getenv("RESEARCH_PRIOR_HYPOTHESES","") or os.getenv("RESEARCH_USED_HYPOTHESIS_IDS","")
 evidence_text=failure.read_text(encoding="utf-8")
 discovery=ROOT/'research'/'discovery'/'latest.json'; discovery_text=discovery.read_text(encoding='utf-8') if discovery.exists() else '{"status":"NO_DISCOVERY_ARTIFACT"}'
 compiled=ROOT/'research'/'discovery'/'compiled_candidates.json'; compiled_text=compiled.read_text(encoding='utf-8') if compiled.exists() else '{"status":"NO_COMPILED_CANDIDATES"}'
 prompt=(f"Parent BC: {parent}\nNext BC: {bc}\nREGISTERED_HYPOTHESES: {json.dumps(sorted(HYPOTHESES))}\nPRIOR_HYPOTHESIS_IDS: {prior}\n\nFAILURE ANALYSIS:\n{evidence_text}\n\nBROAD DISCOVERY ARTIFACT:\n{discovery_text[:30000]}\n\nCOMPILED PRIMITIVES (templates only; choose/propose parameters, never treat them as evidence):\n{compiled_text[:30000]}")
 order=[x.strip().lower() for x in os.getenv("RESEARCH_PROVIDER_ORDER","gemini").split(",") if x.strip()]
 for name in order:
  try:
   candidate=request_candidate(name,prompt)
   if candidate.get("status")=="HOLD": print(f"PROVIDER_{name.upper()}_HOLD"); continue
   base,model,key=config(name); calibrated,issues=verify_with_openai_compatible(base,model,key,candidate,evidence_text)
   if not calibrated: print(f"PROVIDER_CALIBRATION_FAIL {name} issues={json.dumps(issues,sort_keys=True)}",flush=True); continue
   write_candidate(output,candidate); print(f"PROVIDER_SELECTED {name} model={model} hash={candidate['candidate_hash']}"); return 0
  except Exception as exc: print(f"PROVIDER_FAIL {name}: {exc}")
 print("PROVIDER_ROUTER_HOLD"); return 0
if __name__=="__main__":raise SystemExit(main())
