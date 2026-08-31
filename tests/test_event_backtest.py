from datetime import datetime, timezone

import pytest

from engine.event_backtest import EndOfDataExit, build_trades
from engine.events import Direction, MarketBar
from engine.ledger import LedgerTrade


def bar(i, close):
    return MarketBar(
        timestamp=datetime(2026, 1, i, tzinfo=timezone.utc),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
    )


def ledger(entry_bar):
    return LedgerTrade(
        direction=Direction.BULLISH,
        sweep_bar=0,
        mss_bar=1,
        fvg_bar=2,
        entry_bar=entry_bar,
        entry_price=100,
    )


def test_end_of_data_exit():
    bars = [bar(1, 100), bar(2, 105), bar(3, 110)]

    trades = build_trades(
        bars,
        [ledger(1)],
        EndOfDataExit(),
    )

    assert len(trades) == 1
    assert trades[0].entry == 105
    assert trades[0].exit == 110


def test_exit_cannot_be_entry_bar():
    class SameBarExit:
        def exit_bar(self, bars, trade):
            return trade.entry_bar

    with pytest.raises(ValueError):
        build_trades(
            [bar(1, 100), bar(2, 105)],
            [ledger(0)],
            SameBarExit(),
        )


def test_empty_dataset_rejected():
    with pytest.raises(ValueError):
        EndOfDataExit().exit_bar([], ledger(0))
