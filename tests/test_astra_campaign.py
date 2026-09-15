from engine.astra_campaign import load_state, run_campaign


def test_campaign_persists_and_resumes(tmp_path, monkeypatch):
    calls = []

    def fake_build(_):
        def evaluate(candidate):
            calls.append(candidate)
            return type("E", (), {
                "status": "SUCCEEDED",
                "score": float(candidate.get("reward_multiple", 2.0)),
                "result": {"score": float(candidate.get("reward_multiple", 2.0))},
                "failure_class": None,
            })()
        return evaluate

    monkeypatch.setattr("engine.astra_campaign.build_evaluator", fake_build)
    ledger = tmp_path / "ledger.jsonl"
    state = tmp_path / "state.json"

    first = run_campaign("data/BTCUSDT_1h.csv", ledger, state, max_generations=1, generation_limit=2)
    assert first.terminal is True
    assert first.generation == 1
    assert load_state(state).parent["reward_multiple"] == 2.5
    calls_after_first = len(calls)

    resumed = run_campaign("data/BTCUSDT_1h.csv", ledger, state, max_generations=3, generation_limit=2)
    assert resumed.generation == 3
    assert resumed.terminal is True
    assert resumed.parent["reward_multiple"] == 3.5
    assert len(calls) > calls_after_first
