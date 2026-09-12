#!/usr/bin/env python3
"""Fail-closed epistemic calibration gate for model-generated research claims."""
from __future__ import annotations
import json, os
from typing import Any

PROPOSAL_RATIONALE = ("This candidate is a proposed executable test derived from the selected "
    "screen survivor. It does not assert efficacy, causality, market behavior, or any performance result.")
SYSTEM = """You are a strict evidence-calibration verifier.
Verify one candidate against ONE supplied evidence artifact. Do not add facts or repair the candidate.
A hypothesis/proposed test, conceptual change, threshold, direction, or discovery parameter is a PROPOSAL, not evidence.
A proposal-only rationale is not a factual claim and must not be rejected merely because the supplied artifact does not prove the proposed test will work.
FAIL only substantive factual overclaims, unsupported quantitative claims, invented evidence, or established-result claims.
Observations do not establish causation; null results do not prove zero effect or effect-size bounds; sample size alone does not resolve conflicting studies; conflicting evidence must remain visible; do not invent effect sizes, mechanisms, populations, methods, or heterogeneity.
Every substantive factual rationale claim must be traceable to supplied evidence. Evidence-source identifiers are provenance metadata, not factual claims by themselves.
Return JSON only: {"status":"PASS"|"FAIL","issues":[{"code":"...","claim":"...","reason":"..."}]}. PASS requires empty issues."""

def _compact(text: str, limit: int | None = None) -> str:
    limit = limit or max(4000, int(os.getenv("RESEARCH_PROVIDER_CONTEXT_CHAR_LIMIT", "12000")))
    if len(text) <= limit: return text
    head=limit//2; tail=limit-head
    return text[:head]+f"\n...[evidence compacted: {len(text)-limit} chars omitted]...\n"+text[-tail:]

def ground_proposal(candidate: dict[str, Any]) -> None:
    """Replace free-form empirical prose with deterministic proposal-only text."""
    candidate.pop("candidate_hash",None)
    candidate["rationale"] = PROPOSAL_RATIONALE

def verification_prompt(candidate: dict[str, Any], evidence_text: str) -> str:
    candidate_json = json.dumps(candidate,sort_keys=True,ensure_ascii=False)
    return ("CANDIDATE:\n" + candidate_json + "\n\nSUPPLIED EVIDENCE ARTIFACT:\n" + _compact(evidence_text) +
            "\n\nVerify factual claims against only this artifact. Treat the hypothesis and executable parameters as a proposal, not an asserted result. The rationale is intentionally proposal-only; do not invent factual claims that are not present.")

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
    """Calibrate a grounded proposal without a second model call.

    The provider boundary deterministically replaces all free-form empirical prose before
    this gate. Once the exact proposal-only rationale is installed, there is no factual
    claim left for an LLM to adjudicate; using Gemini here only created false-negative
    UNSUPPORTED_CLAIM loops and consumed RPM/TPM. Structural validation remains fail-closed.
    """
    ground_proposal(candidate)
    if candidate.get("rationale") != PROPOSAL_RATIONALE:
        return False,[{"code":"PROPOSAL_GROUNDING_FAILED","claim":str(candidate.get("rationale","")),"reason":"grounded rationale did not match the deterministic proposal-only contract"}]
    return True,[]
