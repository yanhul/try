"""Pre-registered, executable research rules.

These rules are measurable proxies inspired by named trading frameworks. They do
not claim to reproduce a proprietary/book-specific methodology. Thresholds are
fixed here before evaluation so the research agent cannot tune them from OOS.
"""
from __future__ import annotations


def _row(ctx: dict, key: str = "entry") -> dict:
    return ctx.get(key) or ctx.get("sweep") or {}


def _bull(row: dict, direction: str) -> bool:
    return direction == "bullish" and float(row.get("close_location", 0.0)) >= 0.70


def _bear(row: dict, direction: str) -> bool:
    return direction == "bearish" and float(row.get("close_location", 1.0)) <= 0.30


def wyckoff_spring_upthrust(ctx: dict, direction: str) -> bool:
    """Spring/upthrust proxy: extreme relative volume, rejection and directional close."""
    r = _row(ctx, "sweep")
    vr = float(r.get("volume_ratio") or 0.0)
    if vr < 1.5:
        return False
    return (_bull(r, direction) and float(r.get("lower_wick", 0.0)) >= float(r.get("body", 0.0))) or (
        _bear(r, direction) and float(r.get("upper_wick", 0.0)) >= float(r.get("body", 0.0))
    )


def vsa_no_demand_supply(ctx: dict, direction: str) -> bool:
    """VSA proxy: narrow spread + low effort, closing against the attempted move."""
    r = _row(ctx)
    vr = float(r.get("volume_ratio") or 0.0)
    rr = float(r.get("range_ratio") or 0.0)
    loc = float(r.get("close_location", 0.5))
    return vr <= 0.80 and rr <= 0.80 and ((_bear(r, direction) and loc >= 0.50) or (_bull(r, direction) and loc <= 0.50))


def vpa_effort_result(ctx: dict, direction: str) -> bool:
    """VPA proxy: volume expansion confirmed by range expansion and close location."""
    r = _row(ctx)
    vr = float(r.get("volume_ratio") or 0.0)
    rr = float(r.get("range_ratio") or 0.0)
    return vr >= 1.5 and rr >= 1.25 and (_bull(r, direction) or _bear(r, direction))


def gann_range_time_confluence(ctx: dict, direction: str) -> bool:
    """Gann-inspired measurable proxy: normalized range and time-window confluence.

    This is deliberately a proxy, not a claim of classical Gann equivalence.
    A 1x1 relationship is only meaningful after price/time units are specified;
    here we use a fixed normalized range band to make the hypothesis testable.
    """
    r = _row(ctx)
    rr = float(r.get("range_ratio") or 0.0)
    loc = float(r.get("close_location", 0.5))
    return 0.90 <= rr <= 1.10 and ((_bull(r, direction)) or (_bear(r, direction))) and (loc >= 0.70 or loc <= 0.30)


def hank_pruden_effort_confirmation(ctx: dict, direction: str) -> bool:
    """Pruden-inspired effort/result proxy using spread, volume and close location."""
    r = _row(ctx, "sweep")
    vr = float(r.get("volume_ratio") or 0.0)
    rr = float(r.get("range_ratio") or 0.0)
    effort = float(r.get("effort_result") or 0.0)
    return vr >= 1.25 and rr >= 1.0 and effort > 0 and (_bull(r, direction) or _bear(r, direction))


def master_the_trade_trend_pullback(ctx: dict, direction: str) -> bool:
    """Fixed trend/pullback proxy; name is a research handle, not source reproduction."""
    r = _row(ctx)
    rr = float(r.get("range_ratio") or 0.0)
    vr = float(r.get("volume_ratio") or 0.0)
    return rr <= 1.0 and 0.8 <= vr <= 1.2 and ((_bull(r, direction)) or (_bear(r, direction)))


RESEARCH_RULES = {
    "wyckoff_spring_upthrust": wyckoff_spring_upthrust,
    "vsa_no_demand_supply": vsa_no_demand_supply,
    "vpa_effort_result": vpa_effort_result,
    "gann_range_time_confluence": gann_range_time_confluence,
    "hank_pruden_effort_confirmation": hank_pruden_effort_confirmation,
    "master_the_trade_trend_pullback": master_the_trade_trend_pullback,
}
