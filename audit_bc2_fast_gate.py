#!/usr/bin/env python3
"""Strict BC2 fast gate: evaluate only BC2's registered IS/validation evidence."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
candidate = ROOT / "research" / "autonomous_candidates" / "BC2.json"

if not candidate.exists():
    raise SystemExit("BLOCKED: BC2 candidate artifact missing")

data = json.loads(candidate.read_text(encoding="utf-8"))

required = {"bc", "parent_bc", "hypothesis_id", "conceptual_change", "evidence_sources", "rationale", "is_testable", "oos_selection_used", "candidate_hash"}
missing = sorted(required - data.keys())
if missing:
    raise SystemExit(f"BLOCKED: BC2 missing fields: {','.join(missing)}")
if data["bc"] != 2 or data["parent_bc"] != 1:
    raise SystemExit("BLOCKED: BC2 parent/bc mismatch")
if data["oos_selection_used"] is not False:
    raise SystemExit("BLOCKED: BC2 used OOS selection")
if data["is_testable"] is not True:
    raise SystemExit("BLOCKED: BC2 is not testable")
if not isinstance(data["conceptual_change"], str) or not data["conceptual_change"].strip():
    raise SystemExit("BLOCKED: BC2 conceptual_change invalid")
if not isinstance(data["evidence_sources"], list) or not data["evidence_sources"]:
    raise SystemExit("BLOCKED: BC2 evidence_sources missing")

# A candidate cannot be promoted without actual BC2 IS/validation audit evidence.
# Until such evidence exists, strict lifecycle must reject/hold rather than fabricate metrics.
evidence = ROOT / "research" / "bc2_validation_result.json"
if not evidence.exists():
    print("BC2_VALIDATION_EVIDENCE_MISSING")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    raise SystemExit(0)

result = json.loads(evidence.read_text(encoding="utf-8"))
if result.get("oos_selection_used") is True:
    raise SystemExit("BLOCKED: BC2 validation selected using OOS")
if result.get("validation_passed") is True:
    print("BC2_VALIDATION_PASS", result.get("metrics", {}))
    print("PROMOTE_TO_FUTURE_OOS_TEST")
else:
    print("BC2_VALIDATION_FAIL", result.get("metrics", {}))
    print("SPLIT_GATE False")
    print("REJECT_BC")
