from collections import defaultdict

from engine.backtest import load_bars
from engine.data_split import chronological_split
from engine.execution import execute_trades
from engine.ledger import build_ledger
from engine.metrics import Trade, calculate_metrics, trade_return
from engine.risk_exit import FixedRiskRewardExit
from engine.strategy import ReferenceStrategy

DATA = "data/BTCUSDT_1h.csv"
STOP = 0.01
TARGET_R = 2.0
COST = 0.0


def materialize(bars, start, end):
    events = ReferenceStrategy(False).process(bars[:end])
    ledger = [t for t in build_ledger(events) if start <= t.entry_bar < end]
    executed, skipped = execute_trades(
        bars[:end], ledger, FixedRiskRewardExit(STOP, TARGET_R), max_concurrent=1
    )
    executed = [x for x in executed if x.exit.bar_index < end]
    rows = []
    for x in executed:
        t = Trade(
            entry=x.ledger_trade.entry_price,
            exit=x.exit.price,
            direction=x.ledger_trade.direction.value,
            entry_bar=x.ledger_trade.entry_bar,
            exit_bar=x.exit.bar_index,
            exit_reason=x.exit.reason,
        )
        rows.append(t)
    return events, ledger, rows, skipped


def summary(trades):
    if not trades:
        return {"n": 0}
    m = calculate_metrics(trades, COST)
    return {
        "n": len(trades),
        "total_return": m["total_return"],
        "avg_return": m["avg_return"],
        "win_rate": m["win_rate"],
        "profit_factor": m["profit_factor"],
        "max_drawdown": m["max_drawdown"],
    }


def bucket(trades, key):
    out = defaultdict(list)
    for t in trades:
        out[key(t)].append(t)
    return out


def main():
    bars = load_bars(DATA)
    is_split, val_split, oos_split = chronological_split(len(bars))
    print("BC4_1_STATUS", {"purpose": "failure_decomposition", "single_change": None, "oos_touched": False})

    for split in (is_split, val_split):
        events, ledger, trades, skipped = materialize(bars, split.start, split.end)
        print("SPLIT", split.name, {"events": len(events), "ledger": len(ledger), "executed": len(trades), "skipped_overlap": skipped})
        print("OVERALL", summary(trades))

        for name, groups in (
            ("DIRECTION", bucket(trades, lambda t: t.direction)),
            ("EXIT_REASON", bucket(trades, lambda t: t.exit_reason)),
        ):
            print(name)
            for k, g in sorted(groups.items(), key=lambda kv: str(kv[0])):
                print("GROUP", k, summary(g))

        # Chronological thirds expose concentration without introducing a tuned parameter.
        if trades:
            ordered = sorted(trades, key=lambda t: t.entry_bar)
            n = len(ordered)
            cuts = [(0, n // 3), (n // 3, (2 * n) // 3), ((2 * n) // 3, n)]
            print("CHRONOLOGY_THIRDS")
            for idx, (a, b) in enumerate(cuts):
                print("GROUP", idx, summary(ordered[a:b]))

        # Entry-vs-exit diagnostic: raw forward move at fixed 1R/2R horizons.
        # This does not change execution; it only asks whether entries subsequently moved favorably.
        print("FORWARD_MOVE_DIAGNOSTIC")
        for horizon in (1, 3, 6, 12):
            vals = []
            for t in trades:
                if t.entry_bar + horizon >= split.end:
                    continue
                entry = bars[t.entry_bar].close
                future = bars[t.entry_bar + horizon].close
                vals.append((future - entry) / entry if t.direction == "bullish" else (entry - future) / entry)
            if vals:
                wins = sum(v > 0 for v in vals)
                print("HORIZON", horizon, {"n": len(vals), "mean_forward_return": sum(vals) / len(vals), "positive_fraction": wins / len(vals)})
            else:
                print("HORIZON", horizon, {"n": 0})

    print("CAUSE_RULE", "Only a repeatable split-level diagnostic may justify a future single-change hypothesis; no OOS selection.")
    print("OOS_RESERVED", {"start": oos_split.start, "end": oos_split.end, "touched": False})


if __name__ == "__main__":
    main()
