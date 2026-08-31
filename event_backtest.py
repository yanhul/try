from dataclasses import dataclass
from typing import Protocol

from .events import Direction, MarketBar
from .ledger import LedgerTrade
from .metrics import Trade


class ExitPolicy(Protocol):
    def exit_bar(self, bars: list[MarketBar], trade: LedgerTrade) -> int:
        ...


@dataclass(frozen=True)
class EndOfDataExit:
    def exit_bar(self, bars: list[MarketBar], trade: LedgerTrade) -> int:
        if not bars:
            raise ValueError("empty dataset")
        return len(bars) - 1


def build_trades(
    bars: list[MarketBar],
    ledger: list[LedgerTrade],
    exit_policy: ExitPolicy,
) -> list[Trade]:
    trades = []

    for t in ledger:
        if t.entry_bar >= len(bars):
            raise ValueError("entry bar outside dataset")

        exit_bar = exit_policy.exit_bar(bars, t)

        if not 0 <= exit_bar < len(bars):
            raise ValueError("exit bar outside dataset")

        if exit_bar <= t.entry_bar:
            raise ValueError("exit must occur after entry")

        direction = (
            "bullish" if t.direction == Direction.BULLISH
            else "bearish" if t.direction == Direction.BEARISH
            else None
        )

        if direction is None:
            raise ValueError("invalid direction")

        trades.append(
            Trade(
                entry=bars[t.entry_bar].close,
                exit=bars[exit_bar].close,
                direction=direction,
            )
        )

    return trades
