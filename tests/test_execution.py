from datetime import datetime, timezone

from engine.events import Direction, MarketBar
from engine.execution import execute_trades
from engine.ledger import LedgerTrade
from engine.risk_exit import FixedRiskRewardExit


def b(i, o, h, l, c):
    return MarketBar(datetime(2026, 1, i, tzinfo=timezone.utc), o, h, l, c, 1)


def t(entry_bar, direction=Direction.BULLISH):
    return LedgerTrade(direction, 0, 1, 2, entry_bar, 100)


def test_overlapping_entries_are_skipped():
    bars = [b(i, 100, 100, 100, 100) for i in range(1, 8)]
    bars[3] = b(4, 100, 110, 100, 105)  # first trade target
    executed, skipped = execute_trades(bars, [t(2), t(3)], FixedRiskRewardExit(.05, 2))
    assert len(executed) == 1
    assert skipped == 1
