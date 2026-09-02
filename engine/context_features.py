"""Deterministic context features for research hypotheses.

These are measurable proxies, not claims of canonical Wyckoff/Gann doctrine.
All calculations use current/past bars only so they remain causal.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from .events import MarketBar


@dataclass(frozen=True)
class PnFConfig:
    box_size: float
    reversal: int = 3


def rolling_volatility(bars: list[MarketBar], window: int = 20) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    out: list[float | None] = []
    returns: list[float] = []
    for i, bar in enumerate(bars):
        prev = bars[i - 1].close if i else bar.close
        returns.append((bar.close / prev - 1.0) if prev else 0.0)
        sample = returns[max(0, i - window + 1): i + 1]
        if len(sample) < 2:
            out.append(None)
            continue
        avg = sum(sample) / len(sample)
        out.append(sqrt(sum((x - avg) ** 2 for x in sample) / len(sample)))
    return out


def vwap(bars: list[MarketBar]) -> list[float | None]:
    cumulative_pv = 0.0
    cumulative_volume = 0.0
    out: list[float | None] = []
    for b in bars:
        typical = (b.high + b.low + b.close) / 3.0
        cumulative_pv += typical * b.volume
        cumulative_volume += b.volume
        out.append(cumulative_pv / cumulative_volume if cumulative_volume else None)
    return out


def volume_profile(bars: list[MarketBar], bins: int = 20) -> dict[str, object]:
    """Return a deterministic close-price volume profile for the supplied sample."""
    if bins <= 0:
        raise ValueError("bins must be positive")
    if not bars:
        return {"bins": [], "poc": None}
    lo = min(b.low for b in bars)
    hi = max(b.high for b in bars)
    if hi == lo:
        return {"bins": [{"price": lo, "volume": sum(b.volume for b in bars)}], "poc": lo}
    width = (hi - lo) / bins
    bucket_volume = [0.0] * bins
    for b in bars:
        idx = min(bins - 1, max(0, int((b.close - lo) / width)))
        bucket_volume[idx] += b.volume
    levels = [{"price": lo + (i + 0.5) * width, "volume": v} for i, v in enumerate(bucket_volume)]
    poc = max(levels, key=lambda x: x["volume"])["price"]
    return {"bins": levels, "poc": poc}


def point_figure_columns(bars: list[MarketBar], config: PnFConfig) -> list[dict[str, object]]:
    """Build a minimal close-based P&F column sequence."""
    if config.box_size <= 0 or config.reversal < 1:
        raise ValueError("box_size must be positive and reversal >= 1")
    if not bars:
        return []
    columns: list[dict[str, object]] = []
    direction: str | None = None
    extreme = bars[0].close
    for bar in bars[1:]:
        price = bar.close
        if direction is None:
            if price >= extreme + config.box_size:
                direction, extreme = "X", price
            elif price <= extreme - config.box_size:
                direction, extreme = "O", price
            continue
        if direction == "X":
            if price >= extreme + config.box_size:
                extreme = price
            elif price <= extreme - config.reversal * config.box_size:
                columns.append({"direction": direction, "extreme": extreme})
                direction, extreme = "O", price
        else:
            if price <= extreme - config.box_size:
                extreme = price
            elif price >= extreme + config.reversal * config.box_size:
                columns.append({"direction": direction, "extreme": extreme})
                direction, extreme = "X", price
    if direction is not None:
        columns.append({"direction": direction, "extreme": extreme})
    return columns


def gann_reference(bars: list[MarketBar], lookback: int = 20) -> list[dict[str, float | None]]:
    """Expose normalized time/price slope from a rolling anchor; no fixed Gann claim."""
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    out = []
    for i, bar in enumerate(bars):
        start = max(0, i - lookback + 1)
        anchor = bars[start].close
        elapsed = i - start
        slope = ((bar.close - anchor) / elapsed) if elapsed else 0.0
        out.append({"anchor": anchor, "elapsed": float(elapsed), "slope": slope})
    return out
