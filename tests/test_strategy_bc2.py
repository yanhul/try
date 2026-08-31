from datetime import datetime, timedelta

from engine.events import EventType, MarketBar
from engine.strategy_bc2 import BC2SwingSweepStrategy, SWEEP_LOOKBACK


def bar(i, high, low, close=None):
    if close is None:
        close = (high + low) / 2
    return MarketBar(
        timestamp=datetime(2026, 1, 1) + timedelta(hours=i),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1.0,
    )


def sweep_events(bars):
    return [
        e for e in BC2SwingSweepStrategy().process(bars)
        if e.event_type == EventType.LIQUIDITY_SWEEP
    ]


def test_bc2_requires_three_completed_bars_not_only_immediate_previous_bar():
    bars = [
        bar(0, 12, 10, 11),
        bar(1, 11, 8, 10),
        bar(2, 12, 9, 11),
        # Sweeps bar 2's low (9), but not the prior-3 low (8): no sweep.
        bar(3, 12, 8.5, 9.5),
        # Sweeps the actual prior-3 low (8) and closes back above it: bullish sweep.
        bar(4, 12, 7.5, 8.5),
    ]

    events = sweep_events(bars)
    assert len(events) == 1
    assert events[0].bar_index == 4
    assert events[0].direction.value == "bullish"
    assert events[0].price == 8


def test_bc2_sweep_uses_only_completed_bars():
    prefix = [
        bar(0, 12, 10, 11),
        bar(1, 11, 8, 10),
        bar(2, 12, 9, 11),
        bar(3, 12, 7.5, 8.5),
    ]
    future = prefix + [bar(4, 100, 1, 50), bar(5, 200, 0.5, 100)]

    prefix_events = sweep_events(prefix)
    future_events = sweep_events(future)

    assert [e for e in future_events if e.bar_index < len(prefix)] == prefix_events


def test_bc2_declares_locked_lookback():
    assert SWEEP_LOOKBACK == 3
