import hashlib, json
from pathlib import Path

import pytest

from research import bc_controller
from research.bc_controller import append_promotion_event, ensure_oos_state, migrate_legacy_state, verify_oos_receipt
from research.oos_lifecycle import OOSLifecycleError


def test_legacy_evaluation_pointer_cannot_survive_migration():
    evaluation = {
        "bc": 306,
        "candidate_hash": "c306",
        "event_type": "OOS_EVALUATION",
        "oos_state": "OOS_EVALUATED",
        "oos_verdict": "OOS_PASS",
        "oos_executed": True,
        "receipt_digest": "digest",
    }
    state = {
        "history": [{"bc": 306, "decision": "PROMOTE_TO_FUTURE_OOS_TEST", "oos_verdict": "OOS_FAIL"}],
        "oos_evaluation": evaluation,
        "terminal": True,
        "terminal_reason": "OOS_PASS",
    }
    assert migrate_legacy_state(state)
    assert state["oos_evaluation"] is None
    assert state["legacy_oos_evaluation"] == evaluation
    assert state["terminal"] is False
    assert state["terminal_reason"] is None


def test_unknown_resume_rebuilds_only_forward():
    state = {"history": []}
    append_promotion_event(state, 306, "c306")
    state["history"].append({
        "bc": 306,
        "candidate_hash": "c306",
        "oos_state": "UNKNOWN",
        "oos_verdict": None,
        "oos_executed": False,
    })
    ensure_oos_state(state, 306, "c306", "OOS_RECEIPT")
    states = [x["oos_state"] for x in state["history"] if x.get("bc") == 306]
    assert states == ["OOS_PENDING", "UNKNOWN", "OOS_AUTHORIZED", "OOS_DISPATCHED", "OOS_EXECUTED", "OOS_RECEIPT"]


def test_receipt_verifier_recomputes_result_artifact_hash(tmp_path, monkeypatch):
    oos_dir = tmp_path / "oos"
    oos_dir.mkdir()
    monkeypatch.setattr(bc_controller, "OOS_DIR", oos_dir)
    artifact = oos_dir / "BC306_oos_result.json"
    artifact.write_text(json.dumps({"bc": 306, "ok": True}, sort_keys=True), encoding="utf-8")
    result_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    result = {
        "bc": 306,
        "candidate_hash": "c306",
        "oos_executed": True,
        "oos_selection_used": False,
        "oos_passed": False,
        "metrics": {"profit_factor": 0.8},
        "dataset": {"sha256": "d306"},
        "protocol_sha256": "p306",
    }
    receipt = {
        "schema_version": 1,
        "receipt_type": "OOS_EXECUTION_RECEIPT",
        "bc": 306,
        "candidate_hash": "c306",
        "oos_executed": True,
        "oos_selection_used": False,
        "oos_passed": False,
        "metrics": {"profit_factor": 0.8},
        "dataset_sha256": "d306",
        "protocol_sha256": "p306",
        "result_sha256": result_hash,
    }
    receipt_path = oos_dir / "BC306_oos_result_receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert verify_oos_receipt(306, "c306", result, receipt_path)
    artifact.write_text("tampered", encoding="utf-8")
    assert not verify_oos_receipt(306, "c306", result, receipt_path)
