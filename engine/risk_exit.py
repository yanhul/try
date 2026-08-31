from dataclasses import dataclass

from .events import Direction, MarketBar
from .ledger import LedgerTrade


@dataclass(frozen=True)
class ExitResult:
    bar_index: int
    price: float
    reason: str


@dataclass(frozen=True)
class FixedRiskRewardExit:
    stop_fraction: float
    reward_multiple: float

    def __post_init__(self):
        if self.stop_fraction <= 0:
            raise ValueError("stop_fraction must be positive")
        if self.reward_multiple <= 0:
            raise ValueError("reward_multiple must be positive")

    def levels(self, entry: float, direction: Direction):
        if entry <= 0:
            raise ValueError("entry must be positive")
        stop_distance = entry * self.stop_fraction

        if direction == Direction.BULLISH:
            return (
                entry - stop_distance,
                entry + stop_distance * self.reward_multiple,
            )

        if direction == Direction.BEARISH:
            return (
                entry + stop_distance,
                entry - stop_distance * self.reward_multiple,
            )

        raise ValueError("invalid direction")

    def exit(self, bars: list[MarketBar], trade: LedgerTrade) -> ExitResult:
        if not bars:
            raise ValueError("empty dataset")
        if trade.entry_bar < 0 or trade.entry_bar >= len(bars):
            raise ValueError("entry_bar outside dataset")

        # The ledger's entry_price is the execution price. Do not silently
        # replace it with the bar close here.
        entry = trade.entry_price
        stop, target = self.levels(entry, trade.direction)

        for i in range(trade.entry_bar + 1, len(bars)):
            bar = bars[i]

            if trade.direction == Direction.BULLISH:
                # Gap-through handling: a stop/target cannot fill better than
                # the bar open when price has already crossed the level.
                if bar.open <= stop:
                    return ExitResult(i, bar.open, "stop_gap")
                if bar.open >= target:
                    return ExitResult(i, bar.open, "target_gap")

                hit_stop = bar.low <= stop
                hit_target = bar.high >= target

            elif trade.direction == Direction.BEARISH:
                if bar.open >= stop:
                    return ExitResult(i, bar.open, "stop_gap")
                if bar.open <= target:
                    return ExitResult(i, bar.open, "target_gap")

                hit_stop = bar.high >= stop
                hit_target = bar.low <= target
            else:
                raise ValueError("invalid direction")

            # OHLC cannot tell us which level was touched first. The base
            # model therefore resolves same-bar ambiguity conservatively:
            # stop wins.
            if hit_stop:
                return ExitResult(i, stop, "stop")
            if hit_target:
                return ExitResult(i, target, "target")

        return ExitResult(len(bars) - 1, bars[-1].close, "time")

    def exit_bar(self, bars: list[MarketBar], trade: LedgerTrade) -> int:
        return self.exit(bars, trade).bar_index
