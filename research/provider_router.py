#!/usr/bin/env python3
"""Strict multi-provider hypothesis router.

Only failure-analysis text is sent to providers. OOS results/criteria are not
part of the prompt. The local controller remains the authority.
"""
from __future__ import annotations
import json
import os
import urllib.request
from pathlib import Path

SYSTEM = """You are a strict research hypothesis generator. Generate exactly ONE testable next hypothesis from the supplied FAILURE ANALYSIS. Exactly one conceptual change. Cite concrete evidence_sources from the artifact. Never use OOS results to select or tune. Never alter OOS criteria. Never invent missing evidence. Return JSON only with keys: bc,parent_bc,hypothesis_id,conceptual_change,evidence_sources,rationale,is_testable,oos_selection_used. If evidence is insufficient, return {\"status\":\"HOLD\"}."""


def config(name: str):
    n = name.upper()
    defaults = {
        "GEMINI": ("https://generativelanguage.googleapis.com/v1beta/openai/", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"), "GEMINI_API_KEY"),
        "DEEPSEEK": ("https://api.deepseek.com", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"), "DEEPSEEK_API_KEY"),
    }
    if n in defaults:
        base, model, keyvar = defaults[n]
    else:
        base = os.getenv(f"RESEARCH_PROVIDER_{n}_BASE_URL", "")
        model = os.getenv(f"RESEARCH_PROVIDER_{n}_MODEL", "")
        keyvar = f"RESEARCH_PROVIDER_{n}_API_KEY"
    return base.rstrip("/"), model, os.getenv(keyvar, "")


def call(name: str, prompt: str) -> str:
    base, model, key = config(name)
    if not base or not model or not key:
        raise RuntimeError(f"provider_not_configured:{name}")
    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], "max_tokens": 1200, "response_format": {"type": "json_object"}}
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode())
    return data["choices"][0]["message"]["content"]


def main() -> int:
    failure = Path(os.environ["RESEARCH_FAILURE_ANALYSIS"])
    output = Path(os.environ["RESEARCH_CANDIDATE_OUTPUT"])
    bc = int(os.environ["RESEARCH_NEXT_BC"])
    parent = int(os.environ["RESEARCH_PARENT_BC"])
    prompt = f"Parent BC: {parent}\nNext BC: {bc}\nUse ONLY this failure-analysis artifact:\n\n{failure.read_text(encoding='utf-8')}"
    order = [x.strip().lower() for x in os.getenv("RESEARCH_PROVIDER_ORDER", "gemini,deepseek").split(",") if x.strip()]
    errors = []
    for name in order:
        try:
            candidate = json.loads(call(name, prompt))
            if candidate.get("status") == "HOLD":
                print(f"PROVIDER_{name.upper()}_HOLD")
                continue
            candidate["bc"], candidate["parent_bc"] = bc, parent
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"PROVIDER_SELECTED {name} model={config(name)[1]}")
            return 0
        except Exception as exc:
            errors.append(f"{name}:{exc}")
            print(f"PROVIDER_FAIL {name}: {exc}")
    print("PROVIDER_ROUTER_HOLD " + " | ".join(errors))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
