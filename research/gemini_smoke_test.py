#!/usr/bin/env python3
"""Minimal Gemini API smoke test; does not enter or modify research state."""
from __future__ import annotations

import json
import os
import urllib.request


def main() -> int:
    key = os.getenv("GEMINI_API_KEY", "")
    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    if not key:
        raise SystemExit("GEMINI_API_KEY missing")

    url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: GEMINI_SMOKE_OK"}],
        "max_tokens": 16,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"GEMINI_SMOKE_FAIL {type(exc).__name__}: {exc}")

    text = data["choices"][0]["message"]["content"].strip()
    print(f"GEMINI_SMOKE_PASS model={model} response={text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
