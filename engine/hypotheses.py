"""Pre-registered, measurable research hypotheses."""
from __future__ import annotations

from collections.abc import Callable

from .research_rules import RESEARCH_RULES

FeatureRow = dict


def _directional(row: FeatureRow, direction: str) -> tuple[float, float]:
    return float(row["volume_ratio"] or 0.0), float(row["close_location"])


def baseline(_: dict, __: str) -> bool:
    return True


def high_effort_close(row: FeatureRow, direction: str) -> bool:
    vr, loc = _directional(row, direction)
    return vr >= 1.5 and ((direction == "bullish" and loc >= 0.70) or (direction == "bearish" and loc <= 0.30))


def wide_spread_effort(row: FeatureRow, direction: str) -> bool:
    vr, loc = _directional(row, direction)
    rr = float(row["range_ratio"] or 0.0)
    return vr >= 1.5 and rr >= 1.5 and ((direction == "bullish" and loc >= 0.70) or (direction == "bearish" and loc <= 0.30))


def failed_sweep_effort(row: FeatureRow, direction: str) -> bool:
    vr, loc = _directional(row, direction)
    return vr >= 1.2 and ((direction == "bullish" and loc >= 0.80) or (direction == "bearish" and loc <= 0.20))


def sweep_confirmation(ctx: dict, direction: str) -> bool:
    return high_effort_close(ctx["sweep"], direction) if direction in {"bullish", "bearish"} else False


def sweep_wide_effort(ctx: dict, direction: str) -> bool:
    return wide_spread_effort(ctx["sweep"], direction) if direction in {"bullish", "bearish"} else False


def quiet_retest(ctx: dict, direction: str) -> bool:
    row = ctx["entry"]
    vr = float(row["volume_ratio"] or 0.0)
    rr = float(row["range_ratio"] or 0.0)
    return 0.0 < vr <= 0.80 and rr <= 1.0


HYPOTHESES: dict[str, Callable[[dict, str], bool]] = {
    "baseline": lambda ctx, direction: True,
    "sweep_confirmation": sweep_confirmation,
    "sweep_wide_effort": sweep_wide_effort,
    "quiet_retest": quiet_retest,
    **RESEARCH_RULES,
}
