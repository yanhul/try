import json
from pathlib import Path

from research.discovery.absorption import digest


def test_absorption_digest_is_stable():
    assert digest({"b": 2, "a": 1}) == digest({"a": 1, "b": 2})


def test_absorption_proof_schema_after_pipeline(tmp_path, monkeypatch):
    import research.discovery.absorption as absorption
    registry = {
        "records": [{
            "source_id": "SRC-1",
            "url": "https://example.test/a",
            "family": "mean_reversion",
            "is_system": True,
        }]
    }
    queue = {"candidates": [{
        "candidate_id": "Q-1",
        "source_url": "https://example.test/a",
        "family": "mean_reversion",
        "lineage": {"source": "SRC-1", "rounds": [{"decision": "PASS_SOURCE"}, {"decision": "PASS_EXECUTABLE_DATA_LANE"}, {"decision": "PASS_DIVERSITY_DEDUP"}]},
    }]}
    rp, qp, op = tmp_path / "registry.json", tmp_path / "queue.json", tmp_path / "proof.json"
    rp.write_text(json.dumps(registry), encoding="utf-8")
    qp.write_text(json.dumps(queue), encoding="utf-8")
    monkeypatch.setattr(absorption, "REGISTRY", rp)
    monkeypatch.setattr(absorption, "QUEUE", qp)
    monkeypatch.setattr(absorption, "OUT", op)
    assert absorption.main() == 0
    proof = json.loads(op.read_text(encoding="utf-8"))
    assert proof["status"] == "PASS"
    assert proof["absorbed_count"] == 1
    assert proof["absorbed"][0]["status"] == "ABSORBED"
