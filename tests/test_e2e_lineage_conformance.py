import hashlib, json
from pathlib import Path

from research.bc_controller import append_oos_event, append_promotion_event, ensure_oos_state, verify_oos_receipt
from research.oos_lifecycle import OOSLifecycleError, evaluate_oos

def _receipt(result, result_sha):
    r = {
        "schema_version": 1,
        "receipt_type": "OOS_EXECUTION_RECEIPT",
        "bc": result["bc"],
        "candidate_hash": result["candidate_hash"],
        "dataset_sha256": result["dataset"]["sha256"],
        "protocol_sha256": result["protocol_sha256"],
        "result_sha256": result_sha,
        "oos_executed": True,
        "oos_selection_used": False,
        "oos_passed": result["oos_passed"],
        "metrics": result["metrics"],
    }
    r["receipt_id"] = hashlib.sha256(
        json.dumps(r, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return r

def test_exact_lineage_receipt_roundtrip_and_fail_closed(tmp_path, monkeypatch):
    import research.bc_controller as ctl
    monkeypatch.setattr(ctl, "OOS_DIR", tmp_path)

    bc = 9901
    candidate_hash = "c" * 64
    result_payload = {
        "bc": bc,
        "candidate_hash": candidate_hash,
        "oos_executed": True,
        "oos_selection_used": False,
        "oos_passed": False,
        "metrics": {"profit_factor": 0.8, "trade_count": 7},
        "dataset": {"sha256": "d" * 64},
        "protocol_sha256": "p" * 64,
    }
    result_path = tmp_path / f"BC{bc}_oos_result.json"
    result_path.write_text(json.dumps(result_payload, sort_keys=True), encoding="utf-8")
    result_sha = hashlib.sha256(result_path.read_bytes()).hexdigest()

    receipt = _receipt(result_payload, result_sha)
    receipt_path = tmp_path / f"BC{bc}_oos_result_receipt.json"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")

    state = {"history": []}
    append_promotion_event(state, bc, candidate_hash)
    ensure_oos_state(state, bc, candidate_hash, "OOS_RECEIPT",
                     receipt_type=receipt["receipt_type"],
                     receipt_schema_version=receipt["schema_version"],
                     receipt_id=receipt["receipt_id"])
    assert [e["oos_state"] for e in state["history"]] == [
        "OOS_PENDING", "OOS_AUTHORIZED", "OOS_DISPATCHED",
        "OOS_EXECUTED", "OOS_RECEIPT"
    ]

    evaluation = evaluate_oos(result_payload, receipt)
    evaluation_entry = {"bc": bc, "candidate_hash": candidate_hash, **evaluation}
    append_oos_event(state, evaluation_entry)
    assert [e["oos_state"] for e in state["history"]] == [
        "OOS_PENDING", "OOS_AUTHORIZED", "OOS_DISPATCHED",
        "OOS_EXECUTED", "OOS_RECEIPT", "OOS_EVALUATED"
    ]
    assert state["history"][-1]["receipt_digest"] == hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert verify_oos_receipt(bc, candidate_hash, result_payload, receipt_path)

    tampered = dict(receipt)
    tampered["candidate_hash"] = "x" * 64
    receipt_path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")
    assert not verify_oos_receipt(bc, candidate_hash, result_payload, receipt_path)

    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    result_path.write_text("tampered", encoding="utf-8")
    assert not verify_oos_receipt(bc, candidate_hash, result_payload, receipt_path)

def test_unknown_cannot_jump_to_receipt():
    state = {"history": []}
    bc, candidate_hash = 9902, "e" * 64
    append_promotion_event(state, bc, candidate_hash)
    state["history"].append({
        "bc": bc, "candidate_hash": candidate_hash,
        "oos_state": "UNKNOWN", "oos_verdict": None, "oos_executed": False,
    })
    ensure_oos_state(state, bc, candidate_hash, "OOS_RECEIPT",
                     receipt_type="OOS_EXECUTION_RECEIPT",
                     receipt_schema_version=1, receipt_id="r")
    states = [e["oos_state"] for e in state["history"]]
    assert states == [
        "OOS_PENDING", "UNKNOWN", "OOS_AUTHORIZED",
        "OOS_DISPATCHED", "OOS_EXECUTED", "OOS_RECEIPT"
    ]

def test_verdict_without_receipt_is_blocked():
    result = {
        "bc": 9903, "candidate_hash": "f" * 64, "oos_executed": True,
        "oos_selection_used": False, "oos_passed": True,
        "metrics": {"trade_count": 1}, "dataset": {"sha256": "d" * 64},
        "protocol_sha256": "p" * 64,
    }
    try:
        evaluate_oos(result, {})
    except OOSLifecycleError:
        return
    raise AssertionError("verdict without bound receipt was accepted")
