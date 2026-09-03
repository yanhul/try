"""Causal, auditable feature library for strategy research.

Features are deliberately represented as measurable predicates/values rather than
claims that a trading concept is predictive. Each feature can be enabled, disabled,
or tested independently by the research controller.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
import math


FEATURE_CATALOG = {
    "market_structure": ["liquidity_sweep", "mss", "fvg", "retest"],
    "wyckoff": ["range_position", "effort_result"],
    "vsa": ["relative_volume", "spread_volume_relation"],
    "vpa": ["volume_price_confirmation"],
    "vwap": ["vwap_distance"],
    "volume_profile": ["rolling_poc_distance"],
    "mtf": ["higher_timeframe_bias"],
    "volatility": ["atr_fraction", "volatility_regime"],
    "gann": ["normalized_price_slope"],
    "point_figure": ["box_direction"],
}


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    enabled: bool = True
    parameters: dict[str, Any] | None = None

    def canonical(self) -> dict[str, Any]:
        return asdict(self)


def catalog() -> dict[str, list[str]]:
    return {k: list(v) for k, v in FEATURE_CATALOG.items()}


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def causal_features(bars, index: int, lookback: int = 20) -> dict[str, float]:
    """Compute only from bars <= index; never reads future bars."""
    if index < 0 or index >= len(bars):
        raise IndexError(index)
    start = max(0, index - lookback + 1)
    window = bars[start:index + 1]
    b = bars[index]
    ranges = [x.high - x.low for x in window]
    volumes = [x.volume for x in window]
    typical = [(x.high + x.low + x.close) / 3.0 for x in window]
    vol_mean = _mean(volumes)
    range_mean = _mean(ranges)
    pv = sum(t * x.volume for t, x in zip(typical, window))
    vv = sum(x.volume for x in window)
    vwap = pv / vv if vv else b.close
    atr = range_mean
    rolling_high = max(x.high for x in window)
    rolling_low = min(x.low for x in window)
    range_span = rolling_high - rolling_low
    return {
        "relative_volume": b.volume / vol_mean if vol_mean else 1.0,
        "spread_volume_relation": (b.high - b.low) / vol_mean if vol_mean else 0.0,
        "volume_price_confirmation": ((b.close - b.open) / (b.high - b.low)) * (b.volume / vol_mean) if (b.high > b.low and vol_mean) else 0.0,
        "vwap_distance": (b.close - vwap) / b.close if b.close else 0.0,
        "rolling_poc_distance": (b.close - (rolling_high + rolling_low) / 2.0) / b.close if b.close else 0.0,
        "atr_fraction": atr / b.close if b.close else 0.0,
        "volatility_regime": atr / _mean([x.close for x in window]) if window else 0.0,
        "range_position": (b.close - rolling_low) / range_span if range_span else 0.5,
        "normalized_price_slope": (b.close - window[0].close) / window[0].close if window and window[0].close else 0.0,
        "box_direction": 1.0 if b.close > b.open else (-1.0 if b.close < b.open else 0.0),
    }


def evaluate_filters(bars, bar_index: int, filters: dict[str, Any] | None) -> bool:
    """Evaluate explicit numeric filters; absent filters never reject a trade."""
    if not filters:
        return True
    values = causal_features(bars, bar_index, int(filters.get("lookback", 20)))
    for name, rule in filters.items():
        if name == "lookback":
            continue
        if name not in values:
            raise ValueError(f"unknown feature filter: {name}")
        value = values[name]
        if isinstance(rule, dict):
            if "min" in rule and value < float(rule["min"]):
                return False
            if "max" in rule and value > float(rule["max"]):
                return False
        else:
            if not math.isclose(value, float(rule), rel_tol=0.0, abs_tol=1e-12):
                return False
    return True
