"""Causal deterministic adapters for OHLCV-executable trading mechanisms."""
from __future__ import annotations

from .context_features import (
    PnFConfig,
    gann_reference,
    multi_timeframe_context,
    point_figure_directions,
    rolling_volatility,
    rolling_volume_profile_poc,
    vwap,
)
from .events import MarketBar
from .strategy import ReferenceStrategy


def _rolling_mean(values: list[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    out: list[float | None] = []
    for i in range(len(values)):
        sample = values[max(0, i - window + 1): i + 1]
        out.append(sum(sample) / len(sample) if sample else None)
    return out


def momentum_trend(bars: list[MarketBar], window: int = 20) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    closes = [b.close for b in bars]
    return [
        (c / closes[max(0, i - window)] - 1.0) if closes[max(0, i - window)] else None
        for i, c in enumerate(closes)
    ]


def mean_reversion_zscore(bars: list[MarketBar], window: int = 20) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    closes = [b.close for b in bars]
    means = _rolling_mean(closes, window)
    out: list[float | None] = []
    for i, mean in enumerate(means):
        sample = closes[max(0, i - window + 1): i + 1]
        if mean is None or len(sample) < 2:
            out.append(None)
            continue
        sd = (sum((x - mean) ** 2 for x in sample) / len(sample)) ** 0.5
        out.append((closes[i] - mean) / sd if sd else 0.0)
    return out


def volume_spread(bars: list[MarketBar]) -> list[dict[str, float]]:
    """VSA/VPA measurable proxy; not a claim of canonical doctrine."""
    out = []
    for b in bars:
        spread = b.high - b.low
        out.append({
            "spread": spread,
            "volume": b.volume,
            "close_location": (b.close - b.low) / spread if spread else 0.5,
        })
    return out


def family_features(
    bars: list[MarketBar],
    *,
    pnf_box_size: float = 1.0,
    pnf_reversal: int = 3,
) -> dict[str, object]:
    """Return all currently executable OHLCV mechanism adapters.

    External-data families (funding, LOB, on-chain, options, prediction markets,
    MEV) deliberately do not appear here because MarketBar cannot support them.
    """
    events = ReferenceStrategy().process(bars)
    return {
        "momentum_trend": momentum_trend(bars),
        "mean_reversion": mean_reversion_zscore(bars),
        "volatility": rolling_volatility(bars),
        "smc_ict_events": events,
        "fvg_imbalance_events": [e for e in events if e.event_type.value == "FVG"],
        "wyckoff_vsa_vpa": volume_spread(bars),
        "vwap_volume_profile": {"vwap": vwap(bars), "poc": rolling_volume_profile_poc(bars)},
        "regime_proxy": multi_timeframe_context(bars),
        "seasonality": [b.timestamp.weekday() for b in bars],
        "point_figure": point_figure_directions(bars, PnFConfig(pnf_box_size, pnf_reversal)),
        "gann_reference": gann_reference(bars),
    }
