import pytest

from research.oos_lifecycle import (
    OOSLifecycleError,
    OOSState,
    assert_history_entry_legal,
    evaluate_oos,
    promotion_event,
    provider_failure_event,
    terminal_reason_from_oos,
    advance,
)


def valid_result():
    return {
        "bc": 306,
        "candidate_hash": "candidate-306",
        "oos_executed": True,
        "oos_selection_used": False,
        "oos_passed": False,
        "metrics": {"profit_factor": 0.8},
        "dataset": {"sha256": "dataset-306"},
        "protocol_sha256": "protocol-306",
    }


def valid_receipt():
    return {
        "schema_version": 1,
        "receipt_type": "OOS_EXECUTION_RECEIPT",
        "bc": 306,
        "candidate_hash": "candidate-306",
        "dataset_sha256": "dataset-306",
        "protocol_sha256": "protocol-306",
        "oos_executed": True,
        "oos_selection_used": False,
        "oos_passed": False,
        "metrics": {"profit_factor": 0.8},
    }


def test_canonical_state_machine_requires_receipt_before_oos_verdict():
    result = valid_result()
    result["oos_executed"] = False
    with pytest.raises(OOSLifecycleError, match="OOS_VERDICT_REQUIRES_EXECUTION"):
        evaluate_oos(result, valid_receipt())


def test_oos_fail_requires_execution_receipt_and_evaluation():
    evaluation = evaluate_oos(valid_result(), valid_receipt())
    assert evaluation["oos_state"] == OOSState.OOS_EVALUATED
    assert evaluation["oos_verdict"] == OOSState.OOS_FAIL
    assert evaluation["oos_executed"] is True
    assert terminal_reason_from_oos(valid_result(), valid_receipt()) == "OOS_FAIL"


def test_promotion_is_pending_and_has_no_oos_verdict():
    event = promotion_event()
    assert event == {
        "decision": "PROMOTE_TO_FUTURE_OOS_TEST",
        "oos_state": "OOS_PENDING",
        "oos_verdict": None,
        "oos_executed": False,
    }
    assert_history_entry_legal(event)


def test_adversarial_executed_false_plus_oos_fail_is_rejected():
    with pytest.raises(OOSLifecycleError, match="OOS_VERDICT_REQUIRES_EXECUTION"):
        assert_history_entry_legal({
            "decision": "PROMOTE_TO_FUTURE_OOS_TEST",
            "oos_verdict": "OOS_FAIL",
            "oos_executed": False,
        })


def test_promotion_and_evaluation_are_distinct_events():
    promotion = promotion_event()
    evaluation = evaluate_oos(valid_result(), valid_receipt())
    assert_history_entry_legal(promotion)
    assert_history_entry_legal(evaluation)
    assert promotion["oos_verdict"] is None
    assert evaluation["oos_verdict"] == "OOS_FAIL"


def test_adversarial_promotion_cannot_carry_verdict():
    with pytest.raises(OOSLifecycleError, match="PROMOTION_MUST_NOT_CARRY_OOS_VERDICT"):
        assert_history_entry_legal({
            "decision": "PROMOTE_TO_FUTURE_OOS_TEST",
            "oos_verdict": "OOS_FAIL",
            "oos_executed": True,
        })


def test_adversarial_missing_receipt_cannot_be_evaluated():
    with pytest.raises(OOSLifecycleError, match="OOS_VERDICT_REQUIRES_RECEIPT"):
        evaluate_oos(valid_result(), {})


def test_provider_failure_is_not_oos_fail():
    event = provider_failure_event("provider_http_503:GEMINI")
    assert event["oos_state"] == OOSState.PROVIDER_FAIL
    assert event["oos_verdict"] is None
    assert event["oos_executed"] is False


def test_adversarial_receipt_binding_mismatch_is_rejected():
    receipt = valid_receipt()
    receipt["candidate_hash"] = "wrong"
    with pytest.raises(OOSLifecycleError, match="OOS_RECEIPT_BINDING_MISMATCH:candidate_hash"):
        evaluate_oos(valid_result(), receipt)

def test_canonical_transition_graph_rejects_verdict_without_evaluation():
    assert advance(OOSState.OOS_RECEIPT, OOSState.OOS_EVALUATED) == OOSState.OOS_EVALUATED
    with pytest.raises(OOSLifecycleError, match="ILLEGAL_OOS_TRANSITION"):
        advance(OOSState.OOS_DISPATCHED, OOSState.OOS_FAIL)


def test_canonical_transition_graph_separates_provider_failure_from_verdict():
    assert advance(OOSState.OOS_DISPATCHED, OOSState.PROVIDER_FAIL) == OOSState.PROVIDER_FAIL
    with pytest.raises(OOSLifecycleError, match="ILLEGAL_OOS_TRANSITION"):
        advance(OOSState.PROVIDER_FAIL, OOSState.OOS_FAIL)


def test_adversarial_verdict_without_evaluation_event_is_rejected():
    with pytest.raises(OOSLifecycleError, match="OOS_VERDICT_REQUIRES_EVALUATION_EVENT"):
        assert_history_entry_legal({
            "oos_verdict": "OOS_FAIL",
            "oos_executed": True,
            "receipt_digest": "abc",
        })


def test_adversarial_verdict_without_receipt_binding_is_rejected():
    with pytest.raises(OOSLifecycleError, match="OOS_VERDICT_REQUIRES_RECEIPT_BINDING"):
        assert_history_entry_legal({
            "event_type": "OOS_EVALUATION",
            "oos_verdict": "OOS_FAIL",
            "oos_executed": True,
        })
