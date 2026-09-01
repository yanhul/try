#!/usr/bin/env python3
"""Generic strict BC fast gate. Never fabricates performance evidence."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if len(sys.argv) != 2 or not sys.argv[1].isdigit():
    raise SystemExit("usage: audit_bc_fast_gate.py <BC_NUMBER>")
bc = int(sys.argv[1])
if bc < 1:
    raise SystemExit("BLOCKED: BC must be >= 1")

candidate_path = ROOT / "research" / "autonomous_candidates" / f"BC{bc}.json"
failure_path = ROOT / "research" / "failure_analysis" / f"BC{bc}.json"
if not candidate_path.exists():
    raise SystemExit(f"BLOCKED: BC{bc} candidate artifact missing")
data = json.loads(candidate_path.read_text(encoding="utf-8"))
required = {"bc","parent_bc","hypothesis_id","conceptual_change","evidence_sources","rationale","is_testable","oos_selection_used","candidate_hash"}
missing = sorted(required - data.keys())
if missing:
    raise SystemExit(f"BLOCKED: BC{bc} missing fields: {','.join(missing)}")
if int(data["bc"]) != bc or (bc > 1 and int(data["parent_bc"]) != bc - 1):
    raise SystemExit(f"BLOCKED: BC{bc} parent/bc mismatch")
if data["oos_selection_used"] is not False or data["is_testable"] is not True:
    raise SystemExit(f"BLOCKED: BC{bc} provenance/testability violation")
if not isinstance(data["evidence_sources"], list) or not data["evidence_sources"]:
    raise SystemExit(f"BLOCKED: BC{bc} evidence_sources missing")

try:
    from engine.hypotheses import HYPOTHESES
except Exception as exc:
    raise SystemExit(f"BLOCKED: cannot load hypothesis registry: {exc}")

if data["hypothesis_id"] not in HYPOTHESES:
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({"bc":bc,"parent_bc":data["parent_bc"],"decision":"REJECT","reason":"UNEXECUTABLE_HYPOTHESIS_ID","hypothesis_id":data["hypothesis_id"],"conceptual_change":data["conceptual_change"],"evidence_sources":data["evidence_sources"],"oos_selection_used":False,"action":"candidate requires explicit engine implementation before evaluation"}, indent=2) + "\n", encoding="utf-8")
    print(f"BC{bc}_REJECT_UNEXECUTABLE hypothesis_id={data['hypothesis_id']}")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    raise SystemExit(0)

evidence = ROOT / "research" / f"bc{bc}_validation_result.json"
if not evidence.exists():
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({"bc":bc,"parent_bc":data["parent_bc"],"decision":"REJECT","reason":"VALIDATION_EVIDENCE_MISSING","hypothesis_id":data["hypothesis_id"],"evidence_sources":data["evidence_sources"],"oos_selection_used":False,"action":"run registered IS/Validation evaluation before promotion"}, indent=2) + "\n", encoding="utf-8")
    print(f"BC{bc}_VALIDATION_EVIDENCE_MISSING")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    raise SystemExit(0)

result = json.loads(evidence.read_text(encoding="utf-8"))
if result.get("oos_selection_used") is True:
    raise SystemExit(f"BLOCKED: BC{bc} validation selected using OOS")
if result.get("validation_passed") is True:
    print(f"BC{bc}_VALIDATION_PASS", result.get("metrics", {}))
    print("PROMOTE_TO_FUTURE_OOS_TEST")
else:
    print(f"BC{bc}_VALIDATION_FAIL", result.get("metrics", {}))
    print("SPLIT_GATE False")
    print("REJECT_BC")
