"""TradingView-backed universe discovery boundary.

This module is intentionally not part of the historical-price truth path.
It produces a timestamped, hashed candidate-universe snapshot. Candidates
must still be resolved to an authoritative OHLCV source before backtesting.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .tv_screener_adapter import screen_crypto, symbols_from_snapshot


@dataclass(frozen=True)
class UniverseSnapshot:
    schema_version: int
    source: str
    fetched_at: str
    row_count: int
    symbols: tuple[str, ...]
    payload_sha256: str


def _canonical_rows(df: Any) -> list[dict[str, Any]]:
    if not hasattr(df, "to_dict"):
        raise TypeError("df must be a pandas-like DataFrame")
    rows = df.to_dict(orient="records")
    # Normalize pandas scalar-ish values into JSON-compatible primitives.
    return json.loads(json.dumps(rows, default=str, sort_keys=True))


def discover_crypto_universe(
    *,
    fields: Iterable[Any] | None = None,
    filters: Iterable[Any] | None = None,
    limit: int = 100,
) -> tuple[Any, UniverseSnapshot]:
    """Fetch and fingerprint one bounded TradingView universe snapshot."""
    df = screen_crypto(fields=fields, filters=filters, limit=limit)
    rows = _canonical_rows(df)
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    symbols = tuple(symbols_from_snapshot(df))
    return df, UniverseSnapshot(
        schema_version=1,
        source="tradingview:tvscreener",
        fetched_at=datetime.now(timezone.utc).isoformat(),
        row_count=len(rows),
        symbols=symbols,
        payload_sha256=digest,
    )


def persist_snapshot(df: Any, snapshot: UniverseSnapshot, path: str | Path) -> Path:
    """Persist the exact discovery payload plus provenance, never as OHLCV data."""
    rows = _canonical_rows(df)
    payload = {
        "snapshot": asdict(snapshot),
        "rows": rows,
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out


def verify_snapshot(path: str | Path) -> bool:
    """Verify persisted row payload against its recorded SHA-256 fingerprint."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("rows")
    expected = payload.get("snapshot", {}).get("payload_sha256")
    if not isinstance(rows, list) or not isinstance(expected, str):
        raise ValueError("invalid universe snapshot schema")
    canonical = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if actual != expected:
        raise ValueError("universe snapshot integrity failure: payload hash mismatch")
    return True
