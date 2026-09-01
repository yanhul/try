#!/usr/bin/env python3
"""Strict provider router: Gemini proposes; local registry/evidence rules decide."""
from __future__ import annotations
import json, os, urllib.request
from pathlib import Path
from autonomous_hypothesis import load_candidate, write_candidate
from engine.hypotheses import HYPOTHESES

SYSTEM = """You are a strict trading-research hypothesis generator. Generate exactly ONE next hypothesis from FAILURE ANALYSIS.
You may ONLY choose hypothesis_id values from the supplied REGISTERED_HYPOTHESES list. Never invent a new hypothesis_id.
Exactly one conceptual change. Cite only concrete evidence_sources present in the supplied artifact. Never use OOS results to select or tune. Never alter OOS criteria. Never invent missing evidence.
If no unused registered hypothesis can address the failure, return {\"status\":\"HOLD\"}.
Return JSON only with keys: hypothesis_id,conceptual_change,evidence_sources,rationale,is_testable,oos_selection_used.
"""

def config(name: str):
    n=name.upper(); defaults={
        "GEMINI": ("https://generativelanguage.googleapis.com/v1beta/openai/", os.getenv("GEMINI_MODEL","gemini-3.1-flash-lite"), "GEMINI_API_KEY"),
        "DEEPSEEK": ("https://api.deepseek.com", os.getenv("DEEPSEEK_MODEL","deepseek-v4-flash"), "DEEPSEEK_API_KEY")}
    if n in defaults: base,model,keyvar=defaults[n]
    else: base=os.getenv(f"RESEARCH_PROVIDER_{n}_BASE_URL",""); model=os.getenv(f"RESEARCH_PROVIDER_{n}_MODEL",""); keyvar=f"RESEARCH_PROVIDER_{n}_API_KEY"
    return base.rstrip("/"),model,os.getenv(keyvar,"")

def call(name,prompt):
    base,model,key=config(name)
    if not base or not model or not key: raise RuntimeError(f"provider_not_configured:{name}")
    body={"model":model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"max_tokens":1200,"response_format":{"type":"json_object"}}
    req=urllib.request.Request(base+"/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"},method="POST")
    with urllib.request.urlopen(req,timeout=90) as r: return json.loads(r.read().decode())["choices"][0]["message"]["content"]

def main():
    failure=Path(os.environ["RESEARCH_FAILURE_ANALYSIS"]); output=Path(os.environ["RESEARCH_CANDIDATE_OUTPUT"])
    bc=int(os.environ["RESEARCH_NEXT_BC"]); parent=int(os.environ["RESEARCH_PARENT_BC"])
    used={x.strip() for x in os.getenv("RESEARCH_USED_HYPOTHESIS_IDS","").split(",") if x.strip()}
    available=sorted(set(HYPOTHESES)-used)
    if not available:
        print("PROVIDER_ROUTER_HOLD no_unused_registered_hypotheses"); return 0
    prompt=(f"Parent BC: {parent}\nNext BC: {bc}\nREGISTERED_HYPOTHESES: {json.dumps(available)}\n"
            "Use ONLY this failure-analysis artifact:\n\n"+failure.read_text(encoding="utf-8"))
    order=[x.strip().lower() for x in os.getenv("RESEARCH_PROVIDER_ORDER","gemini,deepseek").split(",") if x.strip()]
    for name in order:
        try:
            candidate=json.loads(call(name,prompt))
            if candidate.get("status")=="HOLD": print(f"PROVIDER_{name.upper()}_HOLD"); continue
            if candidate.get("hypothesis_id") not in available: raise ValueError("unregistered_or_already_used_hypothesis_id")
            candidate["bc"],candidate["parent_bc"]=bc,parent
            candidate=load_candidate_from_dict(candidate,bc,parent)
            write_candidate(output,candidate)
            print(f"PROVIDER_SELECTED {name} model={config(name)[1]} hash={candidate['candidate_hash']}")
            return 0
        except Exception as exc: print(f"PROVIDER_FAIL {name}: {exc}")
    print("PROVIDER_ROUTER_HOLD"); return 0

def load_candidate_from_dict(candidate,bc,parent):
    from autonomous_hypothesis import validate_candidate
    ok,reason=validate_candidate(candidate,bc,parent)
    if not ok: raise ValueError(reason)
    return candidate

if __name__=="__main__": raise SystemExit(main())
