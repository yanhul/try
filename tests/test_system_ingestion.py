import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "research/discovery/system_registry.json"


def test_system_ingestion_contract():
    # The generated registry is committed so CI can prove the ingestion contract
    # without relying on a live network response.
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    records = data["records"]
    assert data["total_records"] == len(records)
    assert data["system_records"] == sum(1 for r in records if r["is_system"])
    assert len({r["source_id"] for r in records}) == len(records)
    assert all(r["provenance_only"] is True for r in records)
    assert all(r["executable"] is False for r in records)
    assert all(r["translation_status"] in {"PENDING_INDEPENDENT_TRANSLATION", "NOT_A_SYSTEM_RECORD"} for r in records)


def test_china_lane_is_represented():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert any(r["family"] == "china_a_share" for r in data["records"])
