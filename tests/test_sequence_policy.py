from engine.events import Direction, Event, EventType


def test_canonical_sequence_requires_strict_forward_progression():
    events = [
        Event(None, 10, EventType.LIQUIDITY_SWEEP, Direction.BULLISH, 100),
        Event(None, 11, EventType.MSS, Direction.BULLISH, 101),
        Event(None, 12, EventType.FVG, Direction.BULLISH, 102),
        Event(None, 13, EventType.RETEST, Direction.BULLISH, 103),
    ]
    indexes = [e.bar_index for e in events]
    assert indexes == sorted(indexes)
    assert len(set(indexes)) == 4


def test_same_bar_sweep_and_mss_is_explicitly_detectable():
    events = [
        Event(None, 10, EventType.LIQUIDITY_SWEEP, Direction.BULLISH, 100),
        Event(None, 10, EventType.MSS, Direction.BULLISH, 101),
    ]
    assert events[0].bar_index == events[1].bar_index
