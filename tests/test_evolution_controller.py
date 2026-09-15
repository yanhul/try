import json

import pytest

from engine.evolution_controller import (
    Candidate,
    Evaluation,
    EvolutionController,
    candidate_id,
    mutate,
)
from engine.experiment_ledger import JsonlExperimentLedger


def test_mutation_is_bounded_and_deterministic():
    parent = {"stop_fraction": 0.01, "reward_multiple": 2.0}
    child = mutate(parent, "reward_multiple", 3.0)
    assert child["reward_multiple"] == 3.0
    assert candidate_id(child) == candidate_id(dict(reversed(list(child.items()))))
    with pytest.raises(ValueError):
        mutate(parent, "evaluation_spec", {})


def test_immutable_fields_are_rejected():
    with pytest.raises(ValueError):
        candidate_id({"dataset_identity": "abc", "reward_multiple": 2.0})


def test_crash_is_persisted(tmp_path):
    ledger = JsonlExperimentLedger(tmp_path / "ledger.jsonl")

    def boom(_):
        raise RuntimeError("boom")

    controller = EvolutionController(ledger, boom)
    result = controller.evaluate(Candidate({"reward_multiple": 2.0}))
    assert result.status == "CRASHED"
    records = ledger.read()
    assert [r["status"] for r in records] == ["PROPOSED", "CRASHED"]
    assert records[-1]["failure_class"] == "EXECUTION_EXCEPTION"


def test_propose_preserves_parent_lineage(tmp_path):
    ledger = JsonlExperimentLedger(tmp_path / "ledger.jsonl")
    controller = EvolutionController(ledger, lambda _: Evaluation("PROMOTED", 2.0, {"score": 2.0}))
    parent = Candidate({"reward_multiple": 2.0})
    children = controller.propose(parent, [("reward_multiple", 2.5), ("reward_multiple", 3.0)], limit=2)
    assert len(children) == 2
    assert all(c.parent_id == parent.id for c in children)


def test_compare_requires_success_and_fixed_score():
    baseline = Evaluation("PROMOTED", 2.0, {})
    assert EvolutionController.compare(Evaluation("PROMOTED", 3.0, {}), baseline) == "PROMOTE"
    assert EvolutionController.compare(Evaluation("REJECTED", 9.0, {}), baseline) == "REJECT"
    assert EvolutionController.compare(Evaluation("PROMOTED", 1.0, {}), baseline) == "REJECT"
