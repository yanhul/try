from datetime import datetime, timezone

import pytest

from engine.events import Direction, MarketBar
from engine.ledger import LedgerTrade
from engine.risk_exit import FixedRiskRewardExit


def bar(i, o, h, l, c):
    return MarketBar(datetime(2026, 1, i, tzinfo=timezone.utc), o, h, l, c, 1)


def trade(direction, entry_price=100):
    return LedgerTrade(direction, 0, 1, 1, 1, entry_price)


def test_bullish_target_fills_at_target_not_close():
    result = FixedRiskRewardExit(0.05, 2).exit(
        [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 100, 110, 100, 108)],
        trade(Direction.BULLISH),
    )
    assert result.bar_index == 2
    assert result.price == 110
    assert result.reason == "target"


def test_bearish_target_fills_at_target_not_close():
    result = FixedRiskRewardExit(0.05, 2).exit(
        [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 100, 100, 90, 92)],
        trade(Direction.BEARISH),
    )
    assert result.bar_index == 2
    assert result.price == 90
    assert result.reason == "target"


def test_stop_wins_when_both_hit():
    result = FixedRiskRewardExit(0.05, 2).exit(
        [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 100, 110, 90, 100)],
        trade(Direction.BULLISH),
    )
    assert result.price == 95
    assert result.reason == "stop"


def test_gap_through_stop_uses_open():
    result = FixedRiskRewardExit(0.05, 2).exit(
        [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 90, 95, 85, 88)],
        trade(Direction.BULLISH),
    )
    assert result.price == 90
    assert result.reason == "stop_gap"


def test_entry_price_is_source_of_truth():
    result = FixedRiskRewardExit(0.05, 2).exit(
        [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 100, 116, 100, 110)],
        trade(Direction.BULLISH, entry_price=105),
    )
    assert result.price == pytest.approx(115.5)


@pytest.mark.parametrize("stop,reward", [(0, 2), (-1, 2), (5, 0), (5, -1)])
def test_invalid_parameters(stop, reward):
    with pytest.raises(ValueError):
        FixedRiskRewardExit(stop, reward)
