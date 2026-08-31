from engine.backtest import load_bars
from engine.data_split import chronological_split
from engine.execution import execute_trades
from engine.ledger import build_ledger
from engine.metrics import Trade, calculate_metrics
from engine.risk_exit import FixedRiskRewardExit
from engine.strategy import ReferenceStrategy

DATA = "data/BTCUSDT_1h.csv"
STOP = 0.01
TARGET_R = 2.0
COST = 0.0


def run(strategy, bars, start, end):
    events = strategy.process(bars[:end])
    ledger = [t for t in build_ledger(events) if start <= t.entry_bar < end]
    executed, skipped = execute_trades(bars[:end], ledger, FixedRiskRewardExit(STOP, TARGET_R), max_concurrent=1)
    executed = [x for x in executed if x.exit.bar_index < end]
    trades = [Trade(entry=x.ledger_trade.entry_price, exit=x.exit.price, direction=x.ledger_trade.direction.value, entry_bar=x.ledger_trade.entry_bar, exit_bar=x.exit.bar_index, exit_reason=x.exit.reason) for x in executed]
    return calculate_metrics(trades, COST), len(trades), len(ledger), skipped, len(events)


def main():
    bars = load_bars(DATA)
    is_split, val_split, oos_split = chronological_split(len(bars))
    print("BC4_STATUS", {"purpose": "failure_analysis_only", "single_change": None, "oos_touched": False})
    rows = []
    for split in (is_split, val_split):
        m, n, ledger, skipped, events = run(ReferenceStrategy(False), bars, split.start, split.end)
        row = {"split": split.name, "events": events, "ledger_trades": ledger, "executed_trades": n, "skipped_overlap": skipped, "metrics": m}
        rows.append(row)
        print("BC1_FAILURE_BASE", row)
    print("BC4_DECISION", "NO_NEW_STRATEGY_UNTIL_FAILURE_ANALYSIS_IDENTIFIES_TESTABLE_CAUSE")
    print("OOS_RESERVED", {"start": oos_split.start, "end": oos_split.end, "touched": False})

if __name__ == "__main__":
    main()
