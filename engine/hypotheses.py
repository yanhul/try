"""Pre-registered, measurable research hypotheses."""
from __future__ import annotations

from collections.abc import Callable

from .research_rules import RESEARCH_RULES

FeatureRow = dict


def _directional(row: FeatureRow, direction: str) -> tuple[float, float]:
    return float(row["volume_ratio"] or 0.0), float(row["close_location"])


def high_effort_close(row: FeatureRow, direction: str) -> bool:
    vr, loc = _directional(row, direction)
    return vr >= 1.5 and ((direction == "bullish" and loc >= 0.70) or (direction == "bearish" and loc <= 0.30))


def wide_spread_effort(row: FeatureRow, direction: str) -> bool:
    vr, loc = _directional(row, direction)
    rr = float(row["range_ratio"] or 0.0)
    return vr >= 1.5 and rr >= 1.5 and ((direction == "bullish" and loc >= 0.70) or (direction == "bearish" and loc <= 0.30))


def sweep_confirmation(ctx: dict, direction: str) -> bool:
    return high_effort_close(ctx["sweep"], direction)


def sweep_wide_effort(ctx: dict, direction: str) -> bool:
    return wide_spread_effort(ctx["sweep"], direction)


def quiet_retest(ctx: dict, direction: str) -> bool:
    row = ctx["entry"]
    vr = float(row["volume_ratio"] or 0.0)
    rr = float(row["range_ratio"] or 0.0)
    return 0.0 < vr <= 0.80 and rr <= 1.0


def wyckoff_spring(ctx: dict, direction: str) -> bool:
    return direction == "bullish" and bool(ctx["sweep"].get("wyckoff_spring_proxy"))


def wyckoff_upthrust(ctx: dict, direction: str) -> bool:
    return direction == "bearish" and bool(ctx["sweep"].get("wyckoff_upthrust_proxy"))


def vsa_absorption(ctx: dict, direction: str) -> bool:
    return bool(ctx["entry"].get("vsa_absorption_proxy"))


def vsa_expansion(ctx: dict, direction: str) -> bool:
    return bool(ctx["entry"].get("vsa_volume_expansion") and ctx["entry"].get("vsa_wide_spread"))


def vpa_expansion(ctx: dict, direction: str) -> bool:
    return bool(ctx["entry"].get("vpa_volume_price_expansion"))


def vwap_alignment(ctx: dict, direction: str) -> bool:
    d = ctx["entry"].get("vwap_distance")
    return d is not None and ((direction == "bullish" and d >= 0) or (direction == "bearish" and d <= 0))


def pnf_alignment(ctx: dict, direction: str) -> bool:
    p = ctx["entry"].get("pnf_direction")
    return p == ("X" if direction == "bullish" else "O")


def gann_alignment(ctx: dict, direction: str) -> bool:
    slope = ctx["entry"].get("gann_slope")
    return slope is not None and ((direction == "bullish" and slope > 0) or (direction == "bearish" and slope < 0))


HYPOTHESES: dict[str, Callable[[dict, str], bool]] = {
    "baseline": lambda ctx, direction: True,
    "sweep_confirmation": sweep_confirmation,
    "sweep_wide_effort": sweep_wide_effort,
    "quiet_retest": quiet_retest,
    "wyckoff_spring": wyckoff_spring,
    "wyckoff_upthrust": wyckoff_upthrust,
    "vsa_absorption": vsa_absorption,
    "vsa_expansion": vsa_expansion,
    "vpa_expansion": vpa_expansion,
    "vwap_alignment": vwap_alignment,
    "pnf_alignment": pnf_alignment,
    "gann_alignment": gann_alignment,
    **RESEARCH_RULES,
}
