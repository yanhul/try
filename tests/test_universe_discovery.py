import json

import pytest

from engine.universe_discovery import persist_snapshot, verify_snapshot


class FakeFrame:
    columns = ("name", "close")

    def to_dict(self, orient="records"):
        assert orient == "records"
        return [{"name": "BINANCE:BTCUSDT", "close": 100}]


def test_persisted_universe_snapshot_round_trip(tmp_path):
    from engine.universe_discovery import UniverseSnapshot

    frame = FakeFrame()
    snapshot = UniverseSnapshot(
        schema_version=1,
        source="test",
        fetched_at="2026-01-01T00:00:00+00:00",
        row_count=1,
        symbols=("BINANCE:BTCUSDT",),
        payload_sha256="b3f3c5f4b6c7f7d5f6d0c7e7b3e2b8f7a2f2f7f8d9f0d5f1b8d0a2c3e4f5a6b7",
    )
    # Use the real canonical hash rather than relying on a fabricated digest.
    import hashlib
    canonical = json.dumps(
        frame.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    snapshot = UniverseSnapshot(
        **{**snapshot.__dict__, "payload_sha256": hashlib.sha256(canonical.encode()).hexdigest()}
    )
    path = persist_snapshot(frame, snapshot, tmp_path / "universe.json")
    assert verify_snapshot(path) is True


def test_tampered_universe_snapshot_is_rejected(tmp_path):
    from engine.universe_discovery import UniverseSnapshot
    import hashlib

    frame = FakeFrame()
    canonical = json.dumps(
        frame.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    snapshot = UniverseSnapshot(
        schema_version=1,
        source="test",
        fetched_at="2026-01-01T00:00:00+00:00",
        row_count=1,
        symbols=("BINANCE:BTCUSDT",),
        payload_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
    )
    path = persist_snapshot(frame, snapshot, tmp_path / "universe.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["rows"][0]["close"] = 101
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity failure"):
        verify_snapshot(path)
