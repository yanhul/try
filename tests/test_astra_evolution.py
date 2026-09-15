import json

import pytest

from engine.astra_evolution import (
    AstraEvolutionController,
    DEFAULT_MUTATION_SPACE,
    candidate_hash,
    compare,
    mutate,
    validate_transition,
)
from engine.experiment_ledger import JsonlExperimentLedger


def test_mutation_is_bounded_and_deterministic():
    parent = {"stop_fraction": 0.01, "reward_multiple": 2.0}
    a = mutate(parent, ordinal=0)
    b = mutate(parent, ordinal=0)
    assert a == b
    assert a["stop_fraction"] in DEFAULT_MUTATION_SPACE["stop_fraction"]
    assert a["parent_candidate_hash"] == candidate_hash(parent)


def test_immutable_transition_fails_closed():
    parent = {"stop_fraction": 0.01, "evaluation_spec": {"rr": 2}}
    child = dict(parent, evaluation_spec={"rr": 3})
    with pytest.raises(ValueError, match="immutable_field_changed:evaluation_spec"):
        validate_transition(parent, child)


def test_compare_requires_strict_improvement():
    assert compare({"total_return": 0.2}, {"total_return": 0.1}) == "PROMOTE"
    assert compare({"total_return": 0.1}, {"total_return": 0.1}) == "REJECT"
    assert compare({"missing": 1}, {"total_return": 0.1}) == "REJECT"


def test_controller_records_lineage(tmp_path):
    ledger = JsonlExperimentLedger(tmp_path / "ledger.jsonl")
    controller = AstraEvolutionController(ledger)
    parent = {"stop_fraction": 0.01, "reward_multiple": 2.0}
    child = controller.propose(parent)
    controller.record(
        campaign_id="c1",
        hypothesis_id="h1",
        parent_experiment_id="parent-1",
        config=child,
        status="REJECTED",
        result={"total_return": -0.1},
        decision="REJECT",
    )
    records = ledger.read()
    assert len(records) == 1
    assert records[0]["parent_experiment_id"] == "parent-1"
    assert records[0]["configuration_identity"] == candidate_hash(child)
    assert records[0]["status"] == "REJECTED"
