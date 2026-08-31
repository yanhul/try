"""Descriptive, causal OHLCV feature layer.

This module does not label Wyckoff phases or VSA patterns. It exposes measurable
features that can be used to define and test such hypotheses without changing
the reference strategy baseline.
"""
from __future__ import annotations

from dataclasses import asdict
from statistics import mean, pstdev

from .events import MarketBar


def _rolling(values: list[float], end: int, window: int) -> list[float]:
    start = max(0, end - window + 1)
    return values[start : end + 1]


def extract_features(bars: list[MarketBar], window: int = 20) -> list[dict]:
    if window <= 0:
        raise ValueError("window must be positive")
    if not bars:
        return []

    volumes = [b.volume for b in bars]
    ranges = [b.high - b.low for b in bars]
    closes = [b.close for b in bars]
    out = []

    for i, b in enumerate(bars):
        price_range = b.high - b.low
        body = abs(b.close - b.open)
        location = ((b.close - b.low) / price_range) if price_range > 0 else 0.5
        vr = _rolling(volumes, i, window)
        rr = _rolling(ranges, i, window)
        volume_mean = mean(vr)
        volume_std = pstdev(vr) if len(vr) > 1 else 0.0
        range_mean = mean(rr)

        prev_close = closes[i - 1] if i else b.close
        out.append({
            "timestamp": b.timestamp.isoformat(),
            "bar_index": i,
            "spread": price_range,
            "body": body,
            "upper_wick": b.high - max(b.open, b.close),
            "lower_wick": min(b.open, b.close) - b.low,
            "close_location": location,
            "volume": b.volume,
            "volume_sma": volume_mean,
            "volume_ratio": (b.volume / volume_mean) if volume_mean else None,
            "volume_zscore": ((b.volume - volume_mean) / volume_std) if volume_std else 0.0,
            "range_sma": range_mean,
            "range_ratio": (price_range / range_mean) if range_mean else None,
            "effort_result": (b.volume / price_range) if price_range > 0 else None,
            "return_1": ((b.close - prev_close) / prev_close) if prev_close else None,
            "higher_high": bool(i and b.high > bars[i - 1].high),
            "lower_low": bool(i and b.low < bars[i - 1].low),
        })

    return out
