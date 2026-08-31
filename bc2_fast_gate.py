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
    history = bars[:end]
    events = strategy.process(history)
    ledger = [t for t in build_ledger(events) if start <= t.entry_bar < end]
    executed, skipped = execute_trades(
        history,
        ledger,
        FixedRiskRewardExit(STOP, TARGET_R),
        max_concurrent=1,
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
        "events": sum(1 for e in events if start <= e.bar_index < end),
        "ledger_trades": len(ledger),
        "executed_trades": len(trades),
        "skipped_overlap": skipped,
        "metrics": calculate_metrics(trades, COST),
    }


def score(candidate, baseline):
    cm = candidate["metrics"]
    bm = baseline["metrics"]
    return {
        "return_delta": cm["total_return"] - bm["total_return"],
        "pf_delta": (cm["profit_factor"] or 0.0) - (bm["profit_factor"] or 0.0),
        "dd_delta": cm["max_drawdown"] - bm["max_drawdown"],
        "trade_delta": candidate["executed_trades"] - baseline["executed_trades"],
    }


if __name__ == "__main__":
    bars = load_bars(DATA)
    is_split, val_split, _ = chronological_split(len(bars))

    print("BC2_HYPOTHESIS", {
        "single_change": "liquidity sweep uses prior 3-bar extreme instead of immediately previous bar",
        "sweep_lookback": SWEEP_LOOKBACK,
        "stop": STOP,
        "target_r": TARGET_R,
        "cost": COST,
        "selection_data": "IS+VALIDATION_ONLY",
        "oos_touched": False,
    })

    decisions = []
    for split in (is_split, val_split):
        baseline = run_strategy(ReferenceStrategy(), bars, split.start, split.end)
        candidate = run_strategy(BC2SwingSweepStrategy(), bars, split.start, split.end)
        delta = score(candidate, baseline)
        print("SPLIT", split.name)
        print("BC1", baseline)
        print("BC2", candidate)
        print("DELTA", delta)

        # Fast gate: candidate must improve return on both IS and validation,
        # and may not worsen max drawdown by more than 25% relative.
        bm = baseline["metrics"]
        cm = candidate["metrics"]
        dd_limit = bm["max_drawdown"] * 1.25 if bm["max_drawdown"] > 0 else 0.0
        split_pass = (
            cm["total_return"] > bm["total_return"]
            and cm["max_drawdown"] <= dd_limit
            and candidate["executed_trades"] >= 5
        )
        decisions.append(split_pass)
        print("SPLIT_GATE", split_pass)

    decision = "PROMOTE_TO_FUTURE_OOS_TEST" if all(decisions) else "REJECT_BC2"
    print("DECISION", decision)
    print("RULE", "No current OOS is used for BC2 selection; no parameter search is performed.")
