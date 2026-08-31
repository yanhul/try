from engine.backtest import load_bars
from engine.data_split import chronological_split
from engine.execution import execute_trades
from engine.ledger import build_ledger
from engine.metrics import Trade, calculate_metrics
from engine.risk_exit import FixedRiskRewardExit
from engine.strategy import ReferenceStrategy
from engine.strategy_bc2 import BC2SwingSweepStrategy, SWEEP_LOOKBACK

DATA = "data/BTCUSDT_1h.csv"
STOP = 0.01
TARGET_R = 2.0
COST = 0.0


def run_strategy(strategy, bars, start, end):
    # Full-history processing preserves causal state at the OOS boundary;
    # only trades whose entries and exits are fully inside OOS are scored.
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


if __name__ == "__main__":
    bars = load_bars(DATA)
    is_split, val_split, oos_split = chronological_split(len(bars))

    print("BC2_FUTURE_OOS_CONFIG", {
        "single_change": "liquidity sweep uses prior 3-bar extreme",
        "sweep_lookback": SWEEP_LOOKBACK,
        "stop": STOP,
        "target_r": TARGET_R,
        "cost": COST,
        "selection_data": "IS+VALIDATION_ONLY",
        "oos_start": oos_split.start,
        "oos_end": oos_split.end,
        "oos_touched_before_test": False,
    })

    baseline = run_strategy(ReferenceStrategy(), bars, oos_split.start, oos_split.end)
    candidate = run_strategy(BC2SwingSweepStrategy(), bars, oos_split.start, oos_split.end)
    bm = baseline["metrics"]
    cm = candidate["metrics"]

    print("OOS_BASELINE_BC1", baseline)
    print("OOS_CANDIDATE_BC2", candidate)
    print("OOS_DELTA", {
        "return_delta": cm["total_return"] - bm["total_return"],
        "pf_delta": (cm["profit_factor"] or 0.0) - (bm["profit_factor"] or 0.0),
        "dd_delta": cm["max_drawdown"] - bm["max_drawdown"],
        "trade_delta": candidate["executed_trades"] - baseline["executed_trades"],
    })

    print("OOS_DECISION", "REPORT_ONLY_NO_SELECTION")
    print("RULE", "Future OOS is evaluated once with frozen BC2 parameters; no tuning or selection is performed on OOS.")
