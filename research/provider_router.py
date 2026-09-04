#!/usr/bin/env python3
"""Strict provider router: Gemini drives hypotheses; local registry/evidence rules constrain execution."""
from __future__ import annotations
import json, os, sys, time, urllib.error, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from autonomous_hypothesis import write_candidate
from engine.hypotheses import HYPOTHESES
SYSTEM="""You are the autonomous trading-research hypothesis generator. Generate exactly ONE next hypothesis from the supplied FAILURE ANALYSIS. You may ONLY use hypothesis_id values from REGISTERED_HYPOTHESES; never invent an engine strategy. Reusing a registered hypothesis_id is allowed when the new candidate makes a materially different, evidence-driven conceptual change. Do NOT repeat a prior candidate or merely rename/version it. Exactly one conceptual change. Cite only concrete evidence_sources present in the supplied artifact. Never use OOS results to select or tune. Never alter OOS criteria. Never invent missing evidence. If no materially different executable change is justified, return {\"status\":\"HOLD\"}. Return JSON only with keys: hypothesis_id,conceptual_change,evidence_sources,rationale,is_testable,oos_selection_used."""
def config(name):
 n=name.upper(); defaults={"GEMINI":("https://generativelanguage.googleapis.com/v1beta/openai/",os.getenv("GEMINI_MODEL","gemini-3.1-flash-lite"),"GEMINI_API_KEY"),"DEEPSEEK":("https://api.deepseek.com",os.getenv("DEEPSEEK_MODEL","deepseek-v4-flash"),"DEEPSEEK_API_KEY")}
 if n in defaults: base,model,keyvar=defaults[n]
 else: base=os.getenv(f"RESEARCH_PROVIDER_{n}_BASE_URL",""); model=os.getenv(f"RESEARCH_PROVIDER_{n}_MODEL",""); keyvar=f"RESEARCH_PROVIDER_{n}_API_KEY"
 return base.rstrip("/"),model,os.getenv(keyvar,"")
def call(name,prompt):
 base,model,key=config(name)
 if not base or not model or not key: raise RuntimeError(f"provider_not_configured:{name}")
 body={"model":model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"max_tokens":1200,"response_format":{"type":"json_object"}}
 req=urllib.request.Request(base+"/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"},method="POST")
 for attempt in range(3):
  try:
   with urllib.request.urlopen(req,timeout=90) as r:return json.loads(r.read().decode())["choices"][0]["message"]["content"]
  except urllib.error.HTTPError as exc:
   if exc.code != 429 or attempt == 2: raise
   retry_after=exc.headers.get("Retry-After") if exc.headers else None
   try: delay=max(1,int(float(retry_after))) if retry_after else 65*(attempt+1)
   except ValueError: delay=65*(attempt+1)
   print(f"PROVIDER_RATE_LIMIT {name} retry={attempt+1}/2 delay={delay}s", flush=True)
   time.sleep(delay)
def main():
 failure=Path(os.environ["RESEARCH_FAILURE_ANALYSIS"]); output=Path(os.environ["RESEARCH_CANDIDATE_OUTPUT"]); bc=int(os.environ["RESEARCH_NEXT_BC"]); parent=int(os.environ["RESEARCH_PARENT_BC"])
 # Accept both names so the controller/router contract remains backward-compatible.
 prior=os.getenv("RESEARCH_PRIOR_HYPOTHESES","") or os.getenv("RESEARCH_USED_HYPOTHESIS_IDS","")
 prompt=f"Parent BC: {parent}\nNext BC: {bc}\nREGISTERED_HYPOTHESES: {json.dumps(sorted(HYPOTHESES))}\nPRIOR_HYPOTHESIS_IDS (avoid repeating the same conceptual change): {prior}\nUse ONLY this failure-analysis artifact:\n\n"+failure.read_text(encoding="utf-8")
 for name in [x.strip().lower() for x in os.getenv("RESEARCH_PROVIDER_ORDER","gemini,deepseek").split(",") if x.strip()]:
  try:
   candidate=json.loads(call(name,prompt))
   if candidate.get("status")=="HOLD": print(f"PROVIDER_{name.upper()}_HOLD"); continue
   if candidate.get("hypothesis_id") not in HYPOTHESES: raise ValueError("unregistered_hypothesis_id")
   candidate["bc"],candidate["parent_bc"]=bc,parent
   from autonomous_hypothesis import validate_candidate
   ok,reason=validate_candidate(candidate,bc,parent)
   if not ok: raise ValueError(reason)
   write_candidate(output,candidate); print(f"PROVIDER_SELECTED {name} model={config(name)[1]} hash={candidate['candidate_hash']}"); return 0
  except Exception as exc: print(f"PROVIDER_FAIL {name}: {exc}")
 print("PROVIDER_ROUTER_HOLD"); return 0
if __name__=="__main__":raise SystemExit(main())
