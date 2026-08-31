from __future__ import annotations

from engine.backtest import load_bars
from engine.execution import execute_trades
from engine.ledger import build_ledger
from engine.metrics import Trade, calculate_metrics
from engine.risk_exit import FixedRiskRewardExit
from engine.strategy import ReferenceStrategy


def run(strict: bool) -> dict:
    bars = load_bars("data/BTCUSDT_1h.csv")
    events = ReferenceStrategy(strict_sequence=strict).process(bars)
    ledger = build_ledger(events)
    exit_policy = FixedRiskRewardExit(0.01, 2.0)
    executed, skipped = execute_trades(bars, ledger, exit_policy)

    trades = [
        Trade(
            entry=x.ledger_trade.entry_price,
            exit=x.exit.price,
            direction=x.ledger_trade.direction.value,
            entry_bar=x.ledger_trade.entry_bar,
            exit_bar=x.exit.bar_index,
            exit_reason=x.exit.reason,
        )
        for x in executed
    ]

    return {
        "events": len(events),
        "ledger_trades": len(ledger),
        "executed_trades": len(trades),
        "skipped_overlap": skipped,
        "metrics": calculate_metrics(trades),
    }


if __name__ == "__main__":
    for strict in (False, True):
        print("STRICT", strict)
        result = run(strict)
        for key, value in result.items():
            print(key.upper(), value)
