#!/usr/bin/env python3
"""Fail-closed epistemic calibration gate for model-generated research claims."""
from __future__ import annotations
import json, os, time, urllib.request
from typing import Any

SYSTEM = """You are a strict evidence-calibration verifier.
Verify one candidate against ONE supplied evidence artifact. Do not add facts or repair the candidate.
A hypothesis/proposed test, conceptual change, threshold, direction, or discovery parameter is a PROPOSAL, not evidence.
FAIL only substantive factual overclaims, unsupported quantitative claims, invented evidence, or established-result claims.
Observations do not establish causation; null results do not prove zero effect or effect-size bounds; sample size alone does not resolve conflicting studies; conflicting evidence must remain visible; do not invent effect sizes, mechanisms, populations, methods, or heterogeneity.
Every substantive factual rationale claim must be traceable to supplied evidence.
Return JSON only: {"status":"PASS"|"FAIL","issues":[{"code":"...","claim":"...","reason":"..."}]}. PASS requires empty issues."""

_LAST_VERIFIER_CALL=0.0

def _compact(text: str, limit: int | None = None) -> str:
    limit = limit or max(4000, int(os.getenv("RESEARCH_PROVIDER_CONTEXT_CHAR_LIMIT", "12000")))
    if len(text) <= limit: return text
    head=limit//2; tail=limit-head
    return text[:head]+f"\n...[evidence compacted: {len(text)-limit} chars omitted]...\n"+text[-tail:]

def verification_prompt(candidate: dict[str, Any], evidence_text: str) -> str:
    return ("CANDIDATE:\n" + json.dumps(candidate,sort_keys=True,ensure_ascii=False,separators=(',',':')) +
            "\n\nSUPPLIED EVIDENCE ARTIFACT:\n" + _compact(evidence_text) +
            "\n\nVerify factual claims against only this artifact. Treat the proposed experiment as a proposal, not an asserted result.")

def parse_verdict(text: str) -> tuple[bool,list[dict[str,str]]]:
    data=json.loads(text)
    if not isinstance(data,dict) or data.get("status") not in {"PASS","FAIL"}: raise ValueError("invalid_calibration_verdict")
    issues=data.get("issues",[])
    if not isinstance(issues,list): raise ValueError("invalid_calibration_issues")
    normalized=[]
    for item in issues:
        if not isinstance(item,dict): raise ValueError("invalid_calibration_issue")
        normalized.append({"code":str(item.get("code","")),"claim":str(item.get("claim","")),"reason":str(item.get("reason",""))})
    if data["status"]=="PASS" and normalized: raise ValueError("pass_with_issues")
    return data["status"]=="PASS",normalized

def verify_with_openai_compatible(base_url:str,model:str,api_key:str,candidate:dict[str,Any],evidence_text:str)->tuple[bool,list[dict[str,str]]]:
    global _LAST_VERIFIER_CALL
    if not base_url or not model or not api_key: raise RuntimeError("verifier_not_configured")
    interval=max(4.5,float(os.getenv("RESEARCH_PROVIDER_MIN_INTERVAL_SECONDS","4.5")))
    gap=interval-(time.monotonic()-_LAST_VERIFIER_CALL)
    if gap>0: time.sleep(gap)
    body={"model":model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":verification_prompt(candidate,evidence_text)}],"max_tokens":500,"response_format":{"type":"json_object"}}
    req=urllib.request.Request(base_url.rstrip("/")+"/chat/completions",data=json.dumps(body).encode("utf-8"),headers={"Content-Type":"application/json","Authorization":f"Bearer {api_key}"},method="POST")
    _LAST_VERIFIER_CALL=time.monotonic()
    with urllib.request.urlopen(req,timeout=90) as response: payload=json.loads(response.read().decode("utf-8"))
    return parse_verdict(payload["choices"][0]["message"]["content"])
