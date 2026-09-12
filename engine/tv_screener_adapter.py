"""Optional TradingView Screener adapter for universe discovery.

The adapter is deliberately kept outside the authoritative backtest/data path:
TradingView is an external snapshot source, not a source of truth for historical
research. Raw results must be persisted and passed through the normal integrity
checks before entering experiments.

Dependency is optional. Install with: pip install tvscreener pandas
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class ScreenerSnapshot:
    """Immutable metadata around one external screener snapshot."""

    fetched_at: str
    screener: str
    row_count: int
    columns: tuple[str, ...]


def _load_tvscreener() -> Any:
    try:
        import tvscreener  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "tvscreener is optional; install it with 'pip install tvscreener pandas'"
        ) from exc
    return tvscreener


def screen_crypto(
    *,
    fields: Iterable[Any] | None = None,
    filters: Iterable[Any] | None = None,
    limit: int = 100,
):
    """Fetch a crypto screener snapshot without turning it into research truth.

    ``fields`` and ``filters`` are tvscreener Field expressions. The returned
    DataFrame is intentionally unmodified so downstream integrity code can
    inspect the exact external payload.
    """
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")

    tvs = _load_tvscreener()
    screener = tvs.CryptoScreener()

    if fields:
        screener.select(*tuple(fields))
    if filters:
        for condition in filters:
            screener.where(condition)

    # Keep pagination explicit and bounded. This is discovery, not historical data.
    if hasattr(screener, "set_range"):
        screener.set_range(0, limit)

    return screener.get()


def snapshot_metadata(df: Any, *, screener: str = "tradingview") -> ScreenerSnapshot:
    """Create provenance metadata for a fetched DataFrame."""
    if not hasattr(df, "columns") or not hasattr(df, "__len__"):
        raise TypeError("df must be a pandas-like DataFrame")
    return ScreenerSnapshot(
        fetched_at=datetime.now(timezone.utc).isoformat(),
        screener=screener,
        row_count=len(df),
        columns=tuple(str(c) for c in df.columns),
    )


def symbols_from_snapshot(df: Any, *, symbol_column: str = "name") -> list[str]:
    """Extract candidate symbols only; callers must resolve/validate them later."""
    if symbol_column not in getattr(df, "columns", ()):
        raise ValueError(f"missing symbol column: {symbol_column}")
    values = df[symbol_column].dropna().astype(str).tolist()
    return list(dict.fromkeys(values))
