from datetime import datetime, timezone, timedelta

from engine.events import EventType, Direction, MarketBar
from engine.strategy import ReferenceStrategy


def bar(i, o, h, l, c, v=100):
    return MarketBar(
        timestamp=datetime(
            2026, 1, 1, tzinfo=timezone.utc
        ) + timedelta(minutes=i),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
    )


def event_types(events):
    return [e.event_type for e in events]


def test_bullish_sweep_is_detected():
    bars = [
        bar(0, 100, 105, 95, 100),
        bar(1, 100, 103, 94, 97),
    ]

    events = ReferenceStrategy().process(bars)

    assert event_types(events) == [
        EventType.LIQUIDITY_SWEEP
    ]
    assert events[0].direction == Direction.BULLISH


def test_no_fvg_before_mss():
    bars = [
        bar(0, 100, 105, 95, 100),
        bar(1, 100, 103, 94, 101),
        bar(2, 101, 104, 99, 103),
    ]

    events = ReferenceStrategy().process(bars)

    assert EventType.FVG not in event_types(events)


def test_bullish_mss_and_fvg_and_retest():
    bars = [
        # reference
        bar(0, 100, 105, 95, 100),

        # bullish sweep: below 95, close back above 95
        bar(1, 96, 99, 94, 97),

        # bullish MSS: close above previous high 99
        bar(2, 98, 106, 97, 103),

        # bullish FVG: low 107 > high of bar 1 = 99
        bar(3, 103, 110, 107, 109),

        # retest into [99, 107]
        bar(4, 108, 109, 101, 104),
    ]

    events = ReferenceStrategy().process(bars)

    types = event_types(events)

    assert EventType.LIQUIDITY_SWEEP in types
    assert EventType.MSS in types
    assert EventType.FVG in types
    assert EventType.RETEST in types

    indices = [types.index(x) for x in (
        EventType.LIQUIDITY_SWEEP,
        EventType.MSS,
        EventType.FVG,
        EventType.RETEST,
    )]

    assert indices == sorted(indices)


def test_retest_cannot_happen_on_fvg_creation_bar():
    bars = [
        bar(0, 100, 105, 95, 100),
        bar(1, 96, 99, 94, 97),
        bar(2, 98, 106, 97, 103),
        bar(3, 103, 110, 107, 109),
    ]

    events = ReferenceStrategy().process(bars)

    retests = [
        e for e in events
        if e.event_type == EventType.RETEST
    ]

    assert retests == []


def test_only_one_retest_for_one_fvg():
    bars = [
        bar(0, 100, 105, 95, 100),
        bar(1, 96, 99, 94, 97),
        bar(2, 98, 106, 97, 103),
        bar(3, 103, 110, 107, 109),
        bar(4, 108, 109, 101, 104),
        bar(5, 104, 108, 102, 105),
    ]

    events = ReferenceStrategy().process(bars)

    retests = [
        e for e in events
        if e.event_type == EventType.RETEST
    ]

    assert len(retests) == 1
