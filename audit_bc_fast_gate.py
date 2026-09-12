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
if not isinstance(data["candidate_hash"], str) or not data["candidate_hash"]:
    raise SystemExit(f"BLOCKED: BC{bc} candidate_hash missing")

try:
    from engine.hypotheses import HYPOTHESES
    from engine.autonomous_evaluator import EVALUATION_SPEC
except Exception as exc:
    raise SystemExit(f"BLOCKED: cannot load governing evaluation modules: {exc}")

hid = data["hypothesis_id"]
if hid not in HYPOTHESES and hid != "discovered_primitive":
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({"bc":bc,"parent_bc":data["parent_bc"],"decision":"REJECT","reason":"UNEXECUTABLE_HYPOTHESIS_ID","hypothesis_id":hid,"conceptual_change":data["conceptual_change"],"evidence_sources":data["evidence_sources"],"oos_selection_used":False,"action":"candidate requires explicit engine implementation before evaluation"}, indent=2) + "\n", encoding="utf-8")
    print(f"BC{bc}_REJECT_UNEXECUTABLE hypothesis_id={hid}")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    raise SystemExit(0)

if hid == "discovered_primitive" and not isinstance(data.get("discovery_spec"), dict):
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({"bc":bc,"parent_bc":data["parent_bc"],"decision":"REJECT","reason":"UNEXECUTABLE_DISCOVERY_SPEC","hypothesis_id":hid,"evidence_sources":data["evidence_sources"],"oos_selection_used":False}, indent=2) + "\n", encoding="utf-8")
    print(f"BC{bc}_REJECT_UNEXECUTABLE discovery_spec_missing")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    raise SystemExit(0)

evidence = ROOT / "research" / f"bc{bc}_validation_result.json"
if not evidence.exists():
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({"bc":bc,"parent_bc":data["parent_bc"],"decision":"REJECT","reason":"VALIDATION_EVIDENCE_MISSING","hypothesis_id":hid,"evidence_sources":data["evidence_sources"],"oos_selection_used":False,"action":"run registered IS/Validation evaluation before promotion"}, indent=2) + "\n", encoding="utf-8")
    print(f"BC{bc}_VALIDATION_EVIDENCE_MISSING")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    raise SystemExit(0)

result = json.loads(evidence.read_text(encoding="utf-8"))
# Evidence is authoritative only when it is for this exact candidate and lineage.
try:
    evidence_bc = int(result["bc"])
    evidence_parent = int(result["parent_bc"])
except (KeyError, TypeError, ValueError):
    raise SystemExit(f"BLOCKED: BC{bc} malformed validation lineage")
if evidence_bc != bc or (bc > 1 and evidence_parent != bc - 1):
    raise SystemExit(f"BLOCKED: BC{bc} validation lineage mismatch")
if result.get("candidate_hash") != data["candidate_hash"]:
    raise SystemExit(f"BLOCKED: BC{bc} candidate/evidence hash mismatch")
if result.get("hypothesis_id") != hid:
    raise SystemExit(f"BLOCKED: BC{bc} hypothesis/evidence mismatch")
if result.get("oos_selection_used") is not False or result.get("oos_executed") is True:
    raise SystemExit(f"BLOCKED: BC{bc} OOS contamination")
if result.get("discovery_spec") != data.get("discovery_spec"):
    raise SystemExit(f"BLOCKED: BC{bc} discovery spec/evidence mismatch")
if result.get("evaluation_spec") != EVALUATION_SPEC:
    raise SystemExit(f"BLOCKED: BC{bc} evaluation spec mismatch")

validation = result.get("VALIDATION")
if not isinstance(validation, dict) or not isinstance(validation.get("metrics"), dict):
    raise SystemExit(f"BLOCKED: BC{bc} malformed validation metrics")
if result.get("validation_passed") is True and EVALUATION_SPEC.get("cost_model_status") != "AVAILABLE":
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({"bc":bc,"parent_bc":data["parent_bc"],"decision":"REJECT","reason":"COST_MODEL_REQUIRED","hypothesis_id":hid,"candidate_hash":data["candidate_hash"],"conceptual_change":data["conceptual_change"],"evidence_sources":data["evidence_sources"],"validation_summary":validation,"gross_validation_passed":result.get("gross_validation_passed"),"net_validation_gate":result.get("net_validation_gate"),"oos_selection_used":False,"action":"do not promote until an authoritative cost model is available"}, indent=2) + "\n", encoding="utf-8")
    print(f"BC{bc}_REJECT_COST_MODEL_REQUIRED")
    print("SPLIT_GATE False")
    print("REJECT_BC")
    raise SystemExit(0)
if result.get("validation_passed") is True:
    if result.get("gross_validation_passed") is not True or result.get("net_validation_gate") != "PASS":
        raise SystemExit(f"BLOCKED: BC{bc} inconsistent promotion evidence")
    print(f"BC{bc}_VALIDATION_PASS", validation.get("metrics", {}))
    print("PROMOTE_TO_FUTURE_OOS_TEST")
else:
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(json.dumps({"bc":bc,"parent_bc":data["parent_bc"],"decision":"REJECT","reason":"VALIDATION_FAILED","hypothesis_id":hid,"candidate_hash":data["candidate_hash"],"conceptual_change":data["conceptual_change"],"evidence_sources":data["evidence_sources"],"validation_summary":validation,"gross_validation_passed":result.get("gross_validation_passed"),"net_validation_gate":result.get("net_validation_gate"),"oos_selection_used":False,"action":"reject candidate and require a distinct next hypothesis"}, indent=2) + "\n", encoding="utf-8")
    print(f"BC{bc}_VALIDATION_FAIL", validation.get("metrics", {}))
    print("SPLIT_GATE False")
    print("REJECT_BC")
