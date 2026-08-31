"""Pre-registered, measurable volume/price hypotheses.

These are deliberately simple filters over the existing reference event ledger.
They are not claims that a candle pattern *is* a Wyckoff/VSA label; names are
used only as research handles. Thresholds are fixed before evaluation.
"""
from __future__ import annotations

from collections.abc import Callable


FeatureRow = dict
LedgerLike = object


def _directional(row: FeatureRow, direction: str) -> tuple[float, float]:
    return float(row["volume_ratio"] or 0.0), float(row["close_location"])


def baseline(_: FeatureRow, __: str) -> bool:
    return True


def high_effort_close(row: FeatureRow, direction: str) -> bool:
    """High relative volume with directional close location."""
    vr, loc = _directional(row, direction)
    return vr >= 1.5 and ((direction == "bullish" and loc >= 0.70) or
                          (direction == "bearish" and loc <= 0.30))


def wide_spread_effort(row: FeatureRow, direction: str) -> bool:
    """Wide-range, above-average-volume directional bar."""
    vr, loc = _directional(row, direction)
    rr = float(row["range_ratio"] or 0.0)
    return vr >= 1.5 and rr >= 1.5 and ((direction == "bullish" and loc >= 0.70) or
                                        (direction == "bearish" and loc <= 0.30))


def failed_sweep_effort(row: FeatureRow, direction: str) -> bool:
    """Sweep/rejection-style proxy: relative volume + strong close back in range."""
    vr, loc = _directional(row, direction)
    return vr >= 1.2 and ((direction == "bullish" and loc >= 0.80) or
                          (direction == "bearish" and loc <= 0.20))


def sweep_confirmation(ctx: dict, direction: str) -> bool:
    """Fixed proxy: sweep bar shows elevated effort and closes back directionally."""
    row = ctx["sweep"]
    return high_effort_close(row, direction) if direction in {"bullish", "bearish"} else False


def sweep_wide_effort(ctx: dict, direction: str) -> bool:
    """Fixed proxy: sweep bar is both wide and high-volume with directional close."""
    row = ctx["sweep"]
    return wide_spread_effort(row, direction) if direction in {"bullish", "bearish"} else False


def quiet_retest(ctx: dict, direction: str) -> bool:
    """Fixed low-effort retest proxy: below-average volume and non-wide spread."""
    row = ctx["entry"]
    vr = float(row["volume_ratio"] or 0.0)
    rr = float(row["range_ratio"] or 0.0)
    return 0.0 < vr <= 0.80 and rr <= 1.0


HYPOTHESES: dict[str, Callable[[dict, str], bool]] = {
    "baseline": lambda ctx, direction: True,
    "sweep_confirmation": sweep_confirmation,
    "sweep_wide_effort": sweep_wide_effort,
    "quiet_retest": quiet_retest,
}
