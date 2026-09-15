import pytest

from engine.astra_evaluator import build_evaluator
from engine.evolution_controller import Candidate, Evaluation, EvolutionController, candidate_id, mutate
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
    with pytest.raises(ValueError):
        candidate_id({"candidate_spec": {"promotion_policy": "bad"}})


def test_crash_is_persisted(tmp_path):
    ledger = JsonlExperimentLedger(tmp_path / "ledger.jsonl")

    def boom(_):
        raise RuntimeError("boom")

    result = EvolutionController(ledger, boom).evaluate(Candidate({"reward_multiple": 2.0}))
    assert result.status == "CRASHED"
    records = ledger.read()
    assert [r["status"] for r in records] == ["PROPOSED", "CRASHED"]
    assert records[-1]["failure_class"] == "EXECUTION_EXCEPTION"


def test_propose_preserves_parent_lineage(tmp_path):
    ledger = JsonlExperimentLedger(tmp_path / "ledger.jsonl")
    controller = EvolutionController(ledger, lambda _: Evaluation("SUCCEEDED", 2.0, {"score": 2.0}))
    parent = Candidate({"reward_multiple": 2.0})
    children = controller.propose(parent, [("reward_multiple", 2.5), ("reward_multiple", 3.0)], limit=2)
    assert len(children) == 2
    assert all(c.parent_id == parent.id for c in children)


def test_compare_requires_success_and_score():
    baseline = Evaluation("SUCCEEDED", 2.0, {})
    assert EvolutionController.compare(Evaluation("SUCCEEDED", 3.0, {}), baseline) == "PROMOTE"
    assert EvolutionController.compare(Evaluation("REJECTED", 9.0, {}), baseline) == "REJECT"
    assert EvolutionController.compare(Evaluation("SUCCEEDED", 1.0, {}), baseline) == "REJECT"


def test_decide_persists_separate_promotion_decision(tmp_path):
    ledger = JsonlExperimentLedger(tmp_path / "ledger.jsonl")
    controller = EvolutionController(ledger, lambda _: Evaluation("SUCCEEDED", 3.0, {}))
    candidate = Candidate({"reward_multiple": 3.0})
    evaluation = Evaluation("SUCCEEDED", 3.0, {"score": 3.0})
    baseline = Evaluation("SUCCEEDED", 2.0, {"score": 2.0})
    assert controller.decide(candidate, evaluation, baseline) == "PROMOTE"
    assert ledger.last(candidate.id)["status"] == "PROMOTED"
    assert ledger.last(candidate.id)["decision"] == "PROMOTE"


def test_generation_reuses_terminal_evidence(tmp_path):
    ledger = JsonlExperimentLedger(tmp_path / "ledger.jsonl")
    calls = []

    def evaluator(config):
        calls.append(config)
        return Evaluation("SUCCEEDED", float(config["reward_multiple"]), {"score": float(config["reward_multiple"])})

    controller = EvolutionController(ledger, evaluator)
    parent = Candidate({"reward_multiple": 2.0})
    baseline = Evaluation("SUCCEEDED", 2.0, {"score": 2.0})
    mutations = [("reward_multiple", 3.0), ("reward_multiple", 4.0)]

    best1 = controller.run_generation(parent, mutations, baseline, limit=2)
    best2 = controller.run_generation(parent, mutations, baseline, limit=2)

    assert best1.id == best2.id
    assert best1.config["reward_multiple"] == 4.0
    assert len(calls) == 2
    statuses = [r["status"] for r in ledger.read()]
    assert statuses.count("PROPOSED") == 2
    assert statuses.count("SUCCEEDED") == 2
    assert statuses.count("PROMOTED") == 2


def test_controller_mutation_reaches_real_evaluator(monkeypatch, tmp_path):
    calls = []

    def fake_split(bars, start, end, predicate, stop, rr, **kwargs):
        calls.append((stop, rr, kwargs["pnf_box_fraction"], kwargs["candidate_family"]))
        return {"metrics": {"profit_factor": 1.1, "total_return": rr}, "accepted_signals": 1}

    monkeypatch.setattr("engine.astra_evaluator.evaluate_split", fake_split)
    evaluator = build_evaluator("data/BTCUSDT_1h.csv")
    parent = Candidate({
        "hypothesis_id": "baseline",
        "stop_fraction": 0.01,
        "reward_multiple": 2.0,
        "pnf_box_fraction": 0.01,
    })
    child = Candidate(mutate(parent.config, "reward_multiple", 3.0), parent.id)
    result = evaluator(child.config)
    assert result.status == "SUCCEEDED"
    assert result.score == 3.0
    assert calls == [(0.01, 3.0, 0.01, None), (0.01, 3.0, 0.01, None)]
