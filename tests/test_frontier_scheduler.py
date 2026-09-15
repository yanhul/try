from pathlib import Path
import json

from research.frontier_scheduler import rank_families, select_survivor


def write_candidate(root: Path, name: str, cid: str, family: str):
    path = root / "research" / "autonomous_candidates" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"candidate_hash": cid, "discovery_spec": {"mechanism_family": family}}), encoding="utf-8")


def event(root: Path, cid: str, state: str):
    path = root / "research" / "research_lifecycle.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"candidate_id": cid, "to_state": state}) + "\n")


def test_untried_family_gets_exploration_priority(tmp_path):
    write_candidate(tmp_path, "BC1.json", "a", "momentum_trend")
    event(tmp_path, "a", "REJECTED")
    ranked = rank_families(["momentum_trend", "smc_ict"], tmp_path)
    assert ranked[0].family == "smc_ict"
    assert ranked[0].trials == 0


def test_scheduler_prefers_evidence_without_becoming_promotion_authority(tmp_path):
    write_candidate(tmp_path, "BC1.json", "a", "momentum_trend")
    write_candidate(tmp_path, "BC2.json", "b", "smc_ict")
    event(tmp_path, "a", "PROMOTED")
    event(tmp_path, "b", "REJECTED")
    ranked = rank_families(["momentum_trend", "smc_ict"], tmp_path)
    assert ranked[0].family == "momentum_trend"
    assert not hasattr(ranked[0], "decision")


def test_selection_is_deterministic(tmp_path):
    survivors = [
        {"candidate_id": "b", "family": "smc_ict", "source_url": "https://example/b"},
        {"candidate_id": "a", "family": "smc_ict", "source_url": "https://example/a"},
    ]
    first, _ = select_survivor(survivors, tmp_path)
    second, _ = select_survivor(list(reversed(survivors)), tmp_path)
    assert first["candidate_id"] == second["candidate_id"]
