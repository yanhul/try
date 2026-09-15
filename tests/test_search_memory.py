import json

from research import search_memory
from research.search_memory import rank_families


def _candidate(bc, family, operator="difference"):
    return {"bc": bc, "parent_bc": bc - 1, "candidate_hash": f"hash-{bc}", "hypothesis_id": "discovered_primitive", "discovery_spec": {"mechanism_family": family, "operator": operator, "left": "close", "right": "open", "direction": "up"}}


def _result(passed):
    return {"metrics": {"profit_factor": 1.2 if passed else 0.4, "total_return": 0.1 if passed else -0.2, "max_drawdown": 0.2 if passed else 0.8, "trades": 20}}


def _isolated(monkeypatch, tmp_path):
    root = tmp_path
    monkeypatch.setattr(search_memory, "ROOT", root)
    monkeypatch.setattr(search_memory, "MEMORY_PATH", root / "research" / "search_memory.json")
    monkeypatch.setattr(search_memory, "DURABLE_MEMORY_PATH", root / "research" / "discovery" / ".search_memory.json")


def test_unseen_family_gets_exploration_priority(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    ranked = rank_families(["momentum_trend", "mean_reversion"], seed=1)
    assert set(ranked) == {"momentum_trend", "mean_reversion"}


def test_ranking_is_deterministic_for_same_memory_and_seed(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    assert rank_families(["momentum_trend", "mean_reversion"], seed=7) == rank_families(["momentum_trend", "mean_reversion"], seed=7)


def test_record_is_idempotent_excludes_harness_failures_and_persists_mirror(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    entry = search_memory.record(_candidate(1, "family_a"), _result(False), "OOS_FAIL")
    assert entry["decision"] == "OOS_FAIL"
    assert len(search_memory.load()["events"]) == 1
    assert search_memory.DURABLE_MEMORY_PATH.exists()
    search_memory.record(_candidate(1, "family_a"), _result(False), "OOS_FAIL")
    assert len(search_memory.load()["events"]) == 1
    assert search_memory.record(_candidate(2, "family_b"), {}, "HOLD_PROVIDER_ROUTER") is None
    assert len(search_memory.load()["events"]) == 1


def test_stagnation_changes_search_regime_and_prioritizes_unseen_family(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    for bc in range(1, 9):
        search_memory.record(_candidate(bc, "family_a", operator=f"op{bc}"), _result(False), "OOS_FAIL")
    data = search_memory.load()
    assert data["regime"] == "STAGNANT"
    assert search_memory.rank_families(["family_a", "family_b"], seed=9)[0] == "family_b"


def test_rebuild_from_durable_oos_artifacts_records_learning(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    root = tmp_path
    candidate_dir = root / "research" / "autonomous_candidates"
    oos_dir = root / "research" / "oos"
    candidate_dir.mkdir(parents=True)
    oos_dir.mkdir(parents=True)
    candidate = _candidate(3, "family_c")
    (candidate_dir / "BC3.json").write_text(json.dumps(candidate), encoding="utf-8")
    (oos_dir / "BC3_oos_result.json").write_text(json.dumps({"oos_executed": True, "oos_passed": False, "metrics": {"profit_factor": 0.5}}), encoding="utf-8")
    data = search_memory.rebuild_from_artifacts()
    assert data["families"]["family_c"]["fail"] == 1
    assert len(data["events"]) == 1
