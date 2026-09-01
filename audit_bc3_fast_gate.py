#!/usr/bin/env python3
"""Strict BC3 fast gate; no fabricated performance evidence."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
candidate_path = ROOT / "research" / "autonomous_candidates" / "BC3.json"
failure_path = ROOT / "research" / "failure_analysis" / "BC3.json"

if not candidate_path.exists():
    raise SystemExit("BLOCKED: BC3 candidate artifact missing")
data = json.loads(candidate_path.read_text(encoding="utf-8"))
required = {"bc","parent_bc","hypothesis_id","conceptual_change","evidence_sources","rationale","is_testable","oos_selection_used","candidate_hash"}
missing = sorted(required - data.keys())
if missing:
    raise SystemExit(f"BLOCKED: BC3 missing fields: {','.join(missing)}")
if data["bc"] != 3 or data["parent_bc"] != 2:
    raise SystemExit("BLOCKED: BC3 parent/bc mismatch")
if data["oos_selection_used"] is not False or data["is_testable"] is not True:
    raise SystemExit("BLOCKED: BC3 provenance/testability violation")

from engine.hypotheses import HYPOTHESES
if data["hypothesis_id"] not in HYPOTHESES:
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({
        "bc": 3, "parent_bc": 2, "decision": "REJECT",
        "reason": "UNEXECUTABLE_HYPOTHESIS_ID",
        "hypothesis_id": data["hypothesis_id"],
        "conceptual_change": data["conceptual_change"],
        "evidence_sources": data["evidence_sources"],
        "oos_selection_used": False,
        "action": "candidate requires explicit engine implementation before evaluation"
    }, indent=2) + "\n", encoding="utf-8")
    print(f"BC3_REJECT_UNEXECUTABLE hypothesis_id={data['hypothesis_id']}")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    raise SystemExit(0)

# An executable hypothesis still needs real IS/Validation results.
evidence = ROOT / "research" / "bc3_validation_result.json"
if not evidence.exists():
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({
        "bc": 3, "parent_bc": 2, "decision": "REJECT",
        "reason": "VALIDATION_EVIDENCE_MISSING",
        "hypothesis_id": data["hypothesis_id"],
        "evidence_sources": data["evidence_sources"],
        "oos_selection_used": False,
        "action": "run registered IS/Validation evaluation before promotion"
    }, indent=2) + "\n", encoding="utf-8")
    print("BC3_VALIDATION_EVIDENCE_MISSING")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    raise SystemExit(0)

result = json.loads(evidence.read_text(encoding="utf-8"))
if result.get("oos_selection_used") is True:
    raise SystemExit("BLOCKED: BC3 validation selected using OOS")
if result.get("validation_passed") is True:
    print("BC3_VALIDATION_PASS", result.get("metrics", {}))
    print("PROMOTE_TO_FUTURE_OOS_TEST")
else:
    print("BC3_VALIDATION_FAIL", result.get("metrics", {}))
    print("SPLIT_GATE False")
    print("REJECT_BC")
