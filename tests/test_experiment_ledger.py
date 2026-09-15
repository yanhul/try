from engine.experiment_ledger import ExperimentRecord, JsonlExperimentLedger, identity_hash


def test_ledger_preserves_distinct_attempt_states(tmp_path):
    ledger = JsonlExperimentLedger(tmp_path / "experiments.jsonl")
    ledger.append(ExperimentRecord("e1", "h1", "FAILED", failure_class="CODE_ERROR"))
    ledger.append(ExperimentRecord("e1", "h1", "REJECTED", decision="OOS_FAIL"))
    records = ledger.read()
    assert [r["status"] for r in records] == ["FAILED", "REJECTED"]
    assert ledger.last("e1")["decision"] == "OOS_FAIL"


def test_identity_is_deterministic():
    assert identity_hash({"b": 2, "a": 1}) == identity_hash({"a": 1, "b": 2})


def test_invalid_status_rejected(tmp_path):
    ledger = JsonlExperimentLedger(tmp_path / "experiments.jsonl")
    try:
        ledger.append(ExperimentRecord("e1", "h1", "UNKNOWN"))
    except ValueError:
        pass
    else:
        raise AssertionError("invalid status must be rejected")


def test_unique_terminal_evidence_ignores_rank_and_replay(tmp_path):
    ledger = JsonlExperimentLedger(tmp_path / "experiments.jsonl")
    ledger.append(ExperimentRecord("e1", "h1", "SUCCEEDED", result={"candidate":{"reward_multiple":3.0},"score":3.0}))
    ledger.append(ExperimentRecord("e1", "h1", "RANKED", decision="PREFER"))
    ledger.append(ExperimentRecord("e1", "h1", "SUCCEEDED", result={"candidate":{"reward_multiple":3.0},"score":3.0}))
    evidence = ledger.unique_terminal_evaluations()
    assert list(evidence) == ["e1"]
    assert ledger.terminal_evaluation("e1")["status"] == "SUCCEEDED"
