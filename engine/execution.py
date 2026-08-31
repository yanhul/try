from dataclasses import dataclass

from .ledger import LedgerTrade
from .risk_exit import ExitResult, FixedRiskRewardExit


@dataclass(frozen=True)
class ExecutedTrade:
    ledger_trade: LedgerTrade
    exit: ExitResult


def execute_trades(
    bars,
    ledger: list[LedgerTrade],
    exit_policy: FixedRiskRewardExit,
    max_concurrent: int = 1,
) -> tuple[list[ExecutedTrade], int]:
    """Execute ledger trades with an explicit no-overlap base policy.

    max_concurrent=1 means a new entry is skipped while the previous position
    is open. The policy is deterministic and avoids silently compounding
    overlapping trades without a capital model.
    """
    if max_concurrent != 1:
        raise ValueError("base execution currently supports max_concurrent=1")

    executed: list[ExecutedTrade] = []
    skipped_overlap = 0
    next_entry_allowed = -1

    for trade in sorted(ledger, key=lambda x: (x.entry_bar, x.direction.value)):
        if trade.entry_bar < 0 or trade.entry_bar >= len(bars):
            continue
        if trade.entry_bar < next_entry_allowed:
            skipped_overlap += 1
            continue

        result = exit_policy.exit(bars, trade)
        if result.bar_index <= trade.entry_bar:
            continue

        executed.append(ExecutedTrade(trade, result))
        # Do not allow a second trade on the same exit bar: the base has no
        # intrabar ordering information beyond OHLC.
        next_entry_allowed = result.bar_index + 1

    return executed, skipped_overlap
