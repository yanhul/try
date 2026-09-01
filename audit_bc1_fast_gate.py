#!/usr/bin/env python3
"""Fast gate for the pre-existing baseline: reject when validation evidence fails."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
artifact = ROOT / "research" / "BTCUSDT_1h_hypotheses_v1.json"
data = json.loads(artifact.read_text(encoding="utf-8"))
base = data["hypotheses"]["baseline"]
validation = base["VALIDATION"]

if base.get("validation_passed") is not False:
    raise SystemExit("BLOCKED: BC1 bootstrap gate requires recorded validation_passed=false")

print("BC1_VALIDATION_PASS", validation["metrics"])
print("SPLIT_GATE False")
print("REJECT_BC")
