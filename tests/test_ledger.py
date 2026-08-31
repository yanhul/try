from datetime import datetime, timezone

from engine.events import Direction, Event, EventType
from engine.ledger import build_ledger


def event(i, kind, direction, price=100):
    return Event(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        bar_index=i,
        event_type=kind,
        direction=direction,
        price=price,
    )


def test_complete_bullish_chain():
    events = [
        event(1, EventType.LIQUIDITY_SWEEP, Direction.BULLISH),
        event(2, EventType.MSS, Direction.BULLISH),
        event(3, EventType.FVG, Direction.BULLISH),
        event(4, EventType.RETEST, Direction.BULLISH, 101),
    ]

    trades = build_ledger(events)

    assert len(trades) == 1
    assert trades[0].direction == Direction.BULLISH
    assert trades[0].sweep_bar == 1
    assert trades[0].mss_bar == 2
    assert trades[0].fvg_bar == 3
    assert trades[0].entry_bar == 4
    assert trades[0].entry_price == 101


def test_incomplete_chain_is_not_trade():
    events = [
        event(1, EventType.LIQUIDITY_SWEEP, Direction.BULLISH),
        event(2, EventType.MSS, Direction.BULLISH),
        event(3, EventType.FVG, Direction.BULLISH),
    ]

    assert build_ledger(events) == []


def test_retest_without_chain_is_ignored():
    events = [
        event(4, EventType.RETEST, Direction.BEARISH),
    ]

    assert build_ledger(events) == []


def test_one_fvg_one_retest():
    events = [
        event(1, EventType.LIQUIDITY_SWEEP, Direction.BEARISH),
        event(2, EventType.MSS, Direction.BEARISH),
        event(3, EventType.FVG, Direction.BEARISH),
        event(4, EventType.RETEST, Direction.BEARISH, 99),
        event(5, EventType.RETEST, Direction.BEARISH, 98),
    ]

    assert len(build_ledger(events)) == 1
