"""Deterministic, causal feature families for discretionary market concepts.

These are measurable proxies, not claims that a bar objectively represents a
named Wyckoff/VSA/VPA pattern. They are intentionally composable and suitable
for hypothesis search and regression testing.
"""
from __future__ import annotations

from statistics import mean

from .events import MarketBar


def _sma(values: list[float], i: int, window: int) -> float:
    start = max(0, i - window + 1)
    return mean(values[start : i + 1])


def extract_specific_features(
    bars: list[MarketBar],
    window: int = 20,
) -> list[dict]:
    if window <= 0:
        raise ValueError("window must be positive")
    if not bars:
        return []

    volumes = [b.volume for b in bars]
    ranges = [b.high - b.low for b in bars]
    out: list[dict] = []

    cumulative_pv = 0.0
    cumulative_volume = 0.0
    for i, b in enumerate(bars):
        spread = b.high - b.low
        body = abs(b.close - b.open)
        close_location = ((b.close - b.low) / spread) if spread > 0 else 0.5
        volume_sma = _sma(volumes, i, window)
        range_sma = _sma(ranges, i, window)
        prev = bars[i - 1] if i else b
        prev_range = prev.high - prev.low
        prev_volume = prev.volume

        cumulative_pv += ((b.high + b.low + b.close) / 3.0) * b.volume
        cumulative_volume += b.volume
        vwap = cumulative_pv / cumulative_volume if cumulative_volume else None

        # VSA-style measurable proxies.
        volume_expansion = (b.volume / volume_sma) if volume_sma else None
        wide_spread = (spread / range_sma) if range_sma else None
        effort_result = (b.volume / spread) if spread > 0 else None
        close_strength = close_location
        up_bar = b.close > b.open
        down_bar = b.close < b.open
        volume_up = b.volume > prev_volume
        # High effort with little result: a deliberately simple absorption proxy.
        absorption_proxy = bool(
            volume_expansion is not None
            and volume_expansion >= 1.5
            and wide_spread is not None
            and wide_spread <= 0.8
        )

        # VPA-style measurable relationships.
        price_change = b.close - prev.close
        price_change_pct = (price_change / prev.close) if prev.close else None
        volume_change_pct = (
            (b.volume - prev_volume) / prev_volume if prev_volume else None
        )
        price_volume_ratio = (
            abs(price_change_pct) / volume_expansion
            if price_change_pct is not None and volume_expansion
            else None
        )
        volume_price_expansion = bool(
            volume_expansion is not None
            and volume_expansion >= 1.5
            and wide_spread is not None
            and wide_spread >= 1.2
        )

        # Wyckoff-style proxies based only on observable OHLCV context.
        prior_high = max((x.high for x in bars[max(0, i - window):i]), default=b.high)
        prior_low = min((x.low for x in bars[max(0, i - window):i]), default=b.low)
        spring_proxy = bool(i > 0 and b.low < prior_low and close_location >= 0.7)
        upthrust_proxy = bool(i > 0 and b.high > prior_high and close_location <= 0.3)
        sos_proxy = bool(
            volume_expansion is not None
            and volume_expansion >= 1.5
            and wide_spread is not None
            and wide_spread >= 1.2
            and close_location >= 0.7
        )
        sow_proxy = bool(
            volume_expansion is not None
            and volume_expansion >= 1.5
            and wide_spread is not None
            and wide_spread >= 1.2
            and close_location <= 0.3
        )

        out.append({
            "timestamp": b.timestamp.isoformat(),
            "bar_index": i,
            "vsa_volume_expansion": volume_expansion,
            "vsa_wide_spread": wide_spread,
            "vsa_effort_result": effort_result,
            "vsa_close_strength": close_strength,
            "vsa_up_bar": up_bar,
            "vsa_down_bar": down_bar,
            "vsa_volume_up": volume_up,
            "vsa_absorption_proxy": absorption_proxy,
            "vpa_price_change": price_change,
            "vpa_price_change_pct": price_change_pct,
            "vpa_volume_change_pct": volume_change_pct,
            "vpa_price_volume_ratio": price_volume_ratio,
            "vpa_volume_price_expansion": volume_price_expansion,
            "wyckoff_spring_proxy": spring_proxy,
            "wyckoff_upthrust_proxy": upthrust_proxy,
            "wyckoff_sos_proxy": sos_proxy,
            "wyckoff_sow_proxy": sow_proxy,
            "vwap_session_cumulative": vwap,
        })

    return out
