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


def run_strategy(strategy, bars, start, end):
    # Generate events on data available through the split end, then retain
    # only entries and exits wholly inside the split. No future split data is
    # used to make the decision.
    events = strategy.process(bars[:end])
    ledger = [t for t in build_ledger(events) if start <= t.entry_bar < end]
    executed, skipped = execute_trades(
        bars[:end], ledger, FixedRiskRewardExit(STOP, TARGET_R), max_concurrent=1
    )
    executed = [x for x in executed if x.exit.bar_index < end]
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
        "events": sum(start <= e.bar_index < end for e in events),
        "ledger_trades": len(ledger),
        "executed_trades": len(trades),
        "skipped_overlap": skipped,
        "metrics": calculate_metrics(trades, COST),
    }


def main():
    bars = load_bars(DATA)
    is_split, val_split, oos_split = chronological_split(len(bars))

    print("BC3_HYPOTHESIS", {
        "single_change": "MSS must occur strictly after the liquidity-sweep bar",
        "strict_sequence": True,
        "stop": STOP,
        "target_r": TARGET_R,
        "cost": COST,
        "selection_data": "IS+VALIDATION_ONLY",
        "oos_touched": False,
    })

    decisions = []
    for split in (is_split, val_split):
        baseline = run_strategy(ReferenceStrategy(False), bars, split.start, split.end)
        candidate = run_strategy(ReferenceStrategy(True), bars, split.start, split.end)
        bm, cm = baseline["metrics"], candidate["metrics"]
        dd_limit = bm["max_drawdown"] * 1.25 if bm["max_drawdown"] > 0 else 0.0
        gate = (
            cm["total_return"] > bm["total_return"]
            and cm["max_drawdown"] <= dd_limit
            and candidate["executed_trades"] >= 5
        )
        print("SPLIT", split.name)
        print("BC1", baseline)
        print("BC3", candidate)
        print("DELTA", {
            "return_delta": cm["total_return"] - bm["total_return"],
            "pf_delta": (cm["profit_factor"] or 0.0) - (bm["profit_factor"] or 0.0),
            "dd_delta": cm["max_drawdown"] - bm["max_drawdown"],
            "trade_delta": candidate["executed_trades"] - baseline["executed_trades"],
        })
        print("SPLIT_GATE", gate)
        decisions.append(gate)

    decision = "PROMOTE_TO_FUTURE_OOS_TEST" if all(decisions) else "REJECT_BC3"
    print("DECISION", decision)
    print("OOS_SPLIT_RESERVED", {
        "start": oos_split.start,
        "end": oos_split.end,
        "rule": "OOS is reserved and must not be used unless both IS and validation gates pass.",
    })


if __name__ == "__main__":
    main()
