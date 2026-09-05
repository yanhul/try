#!/usr/bin/env python3
"""Fail-closed epistemic calibration gate for model-generated research claims.

This gate does not decide the research policy or promotion criteria. It only checks
whether a model-generated candidate/rationale is supported by the supplied failure
analysis and whether quantitative claims are warranted by the supplied evidence.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

SYSTEM = """You are a strict evidence-calibration verifier.
You verify a model-generated research candidate against ONE supplied evidence artifact.
Do not add facts from outside the artifact. Do not repair the candidate yourself.
Classify unsupported or overstated reasoning as FAIL.

Rules:
- An observation/association does not establish causation.
- A null statistical result does not prove zero effect.
- A null result alone does not establish a quantitative effect-size bound.
- A confidence interval may justify only the bounds explicitly supplied by the artifact.
- Sample size alone does not determine the winner between conflicting studies.
- One positive study does not establish replication.
- Conflicting evidence must remain visible; do not resolve conflict by deletion.
- Retracted evidence cannot be treated as current positive evidence.
- Do not invent effect sizes, confidence intervals, mechanisms, populations, methods,
  or explanatory heterogeneity not present in the supplied artifact.
- Every substantive rationale claim must be traceable to supplied evidence.

Return JSON only:
{"status":"PASS"|"FAIL","issues":[{"code":"...","claim":"...","reason":"..."}]}
Use FAIL if any substantive overclaim, unsupported inference, invented quantitative
bound, or ungrounded explanatory claim is present. Empty issues are required for PASS.
"""


def verification_prompt(candidate: dict[str, Any], evidence_text: str) -> str:
    return (
        "CANDIDATE:\n"
        + json.dumps(candidate, sort_keys=True, ensure_ascii=False)
        + "\n\nSUPPLIED EVIDENCE ARTIFACT:\n"
        + evidence_text
        + "\n\nVerify the candidate against only this artifact."
    )


def parse_verdict(text: str) -> tuple[bool, list[dict[str, str]]]:
    data = json.loads(text)
    if not isinstance(data, dict) or data.get("status") not in {"PASS", "FAIL"}:
        raise ValueError("invalid_calibration_verdict")
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("invalid_calibration_issues")
    normalized: list[dict[str, str]] = []
    for item in issues:
        if not isinstance(item, dict):
            raise ValueError("invalid_calibration_issue")
        normalized.append({
            "code": str(item.get("code", "")),
            "claim": str(item.get("claim", "")),
            "reason": str(item.get("reason", "")),
        })
    if data["status"] == "PASS" and normalized:
        raise ValueError("pass_with_issues")
    return data["status"] == "PASS", normalized


def verify_with_openai_compatible(base_url: str, model: str, api_key: str,
                                  candidate: dict[str, Any], evidence_text: str) -> tuple[bool, list[dict[str, str]]]:
    if not base_url or not model or not api_key:
        raise RuntimeError("verifier_not_configured")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": verification_prompt(candidate, evidence_text)},
        ],
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = payload["choices"][0]["message"]["content"]
    return parse_verdict(text)
