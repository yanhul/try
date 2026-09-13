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

    assert event_types(events) == [EventType.LIQUIDITY_SWEEP]
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
        bar(0, 100, 105, 95, 100),
        bar(1, 96, 99, 94, 97),
        bar(2, 98, 106, 97, 103),
        bar(3, 103, 110, 107, 109),
        bar(4, 108, 109, 107, 107.5),
    ]

    events = ReferenceStrategy().process(bars)
    types = event_types(events)

    assert EventType.LIQUIDITY_SWEEP in types
    assert EventType.MSS in types
    assert EventType.FVG in types
    assert EventType.RETEST in types

    event_by_type = {event.event_type: event for event in events}
    assert event_by_type[EventType.LIQUIDITY_SWEEP].bar_index < event_by_type[EventType.MSS].bar_index
    assert event_by_type[EventType.MSS].bar_index < event_by_type[EventType.FVG].bar_index
    assert event_by_type[EventType.FVG].bar_index < event_by_type[EventType.RETEST].bar_index


def test_retest_cannot_happen_on_fvg_creation_bar():
    bars = [
        bar(0, 100, 105, 95, 100),
        bar(1, 96, 99, 94, 97),
        bar(2, 98, 106, 97, 103),
        bar(3, 103, 110, 107, 109),
    ]

    events = ReferenceStrategy().process(bars)
    retests = [e for e in events if e.event_type == EventType.RETEST]

    assert retests == []


def test_only_one_retest_for_one_fvg():
    bars = [
        bar(0, 100, 105, 95, 100),
        bar(1, 96, 99, 94, 97),
        bar(2, 98, 106, 97, 103),
        bar(3, 103, 110, 107, 109),
        bar(4, 108, 109, 107, 107.5),
        bar(5, 104, 108, 102, 105),
    ]

    events = ReferenceStrategy().process(bars)
    retests = [e for e in events if e.event_type == EventType.RETEST]

    assert len(retests) == 1


def test_mss_must_follow_sweep_on_a_later_bar():
    bars = [
        bar(0, 100, 105, 95, 100),
        # Same candle sweeps below the low and closes above the prior high.
        # It must remain a sweep only; MSS requires a later bar.
        bar(1, 100, 108, 94, 106),
        bar(2, 106, 110, 105, 109),
    ]

    events = ReferenceStrategy().process(bars)

    assert [e.event_type for e in events] == [
        EventType.LIQUIDITY_SWEEP,
        EventType.MSS,
    ]
    assert events[0].bar_index == 1
    assert events[1].bar_index == 2


def test_fvg_must_follow_mss_on_a_later_bar():
    bars = [
        bar(0, 100, 105, 95, 100),
        bar(1, 96, 99, 94, 97),
        # MSS and a geometrically valid FVG can coincide here, but the
        # reference sequence requires FVG on a later candle.
        bar(2, 98, 108, 106, 107),
        bar(3, 107, 112, 109, 110),
    ]

    events = ReferenceStrategy().process(bars)
    fvg_events = [e for e in events if e.event_type == EventType.FVG]

    assert fvg_events
    mss = next(e for e in events if e.event_type == EventType.MSS)
    assert fvg_events[0].bar_index > mss.bar_index


def test_new_sweep_invalidates_stale_fvg():
    bars = [
        bar(0, 100, 105, 95, 100),
        bar(1, 96, 99, 94, 97),
        bar(2, 98, 106, 97, 103),
        bar(3, 103, 110, 107, 109),
        # This bearish sweep overlaps the old bullish FVG. It must invalidate
        # the old zone instead of emitting a stale bullish retest.
        bar(4, 108, 109, 101, 104),
    ]

    events = ReferenceStrategy().process(bars)

    assert any(
        e.event_type == EventType.LIQUIDITY_SWEEP
        and e.direction == Direction.BEARISH
        and e.bar_index == 4
        for e in events
    )
    assert not any(
        e.event_type == EventType.RETEST and e.bar_index == 4
        for e in events
    )
