#!/usr/bin/env python3
"""Strict BC2 gate: only executable, evidence-backed candidates may advance."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
candidate_path = ROOT / "research" / "autonomous_candidates" / "BC2.json"
failure_path = ROOT / "research" / "failure_analysis" / "BC2.json"

if not candidate_path.exists():
    raise SystemExit("BLOCKED: BC2 candidate artifact missing")
data = json.loads(candidate_path.read_text(encoding="utf-8"))
required = {"bc","parent_bc","hypothesis_id","conceptual_change","evidence_sources","rationale","is_testable","oos_selection_used","candidate_hash"}
missing = sorted(required - data.keys())
if missing:
    raise SystemExit(f"BLOCKED: BC2 missing fields: {','.join(missing)}")
if data["bc"] != 2 or data["parent_bc"] != 1:
    raise SystemExit("BLOCKED: BC2 parent/bc mismatch")
if data["oos_selection_used"] is not False or data["is_testable"] is not True:
    raise SystemExit("BLOCKED: BC2 provenance/testability violation")

# The current research engine only executes pre-registered hypothesis IDs.
# Do not silently reinterpret an agent proposal as executable code.
from engine.hypotheses import HYPOTHESES
if data["hypothesis_id"] not in HYPOTHESES:
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({
        "bc": 2,
        "parent_bc": 1,
        "decision": "REJECT",
        "reason": "UNEXECUTABLE_HYPOTHESIS_ID",
        "hypothesis_id": data["hypothesis_id"],
        "conceptual_change": data["conceptual_change"],
        "evidence_sources": data["evidence_sources"],
        "oos_selection_used": False,
        "action": "candidate requires an explicit engine implementation before evaluation"
    }, indent=2) + "\n", encoding="utf-8")
    print(f"BC2_REJECT_UNEXECUTABLE hypothesis_id={data['hypothesis_id']}")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    raise SystemExit(0)

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
