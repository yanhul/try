from collections import defaultdict
import csv
from engine.events import MarketBar
from engine.strategy import ReferenceStrategy
from engine.ledger import build_ledger
from engine.execution import execute_trades
from engine.risk_exit import FixedRiskRewardExit
from engine.walk_forward import generate_walk_forward

DATA = "data/BTCUSDT_1h.csv"
TRAIN = 1100
TEST = 500
STEP = 500


def load_bars():
    with open(DATA, newline="", encoding="utf-8-sig") as f:
        return [
            MarketBar(
                timestamp=r["timestamp"],
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["volume"]),
            )
            for r in csv.DictReader(f)
        ]


def outcome(executed):
    rows = []
    for x in executed:
        t = x.ledger_trade
        e = t.entry_price
        p = x.exit.price
        d = t.direction.value
        r = (p / e - 1.0) if d == "bullish" else (e / p - 1.0)
        rows.append(
            {
                "direction": d,
                "sweep_to_mss": t.mss_bar - t.sweep_bar,
                "mss_to_fvg": t.fvg_bar - t.mss_bar,
                "fvg_to_retest": t.entry_bar - t.fvg_bar,
                "sequence_bars": t.entry_bar - t.sweep_bar,
                "entry_bar": t.entry_bar,
                "exit_bar": x.exit.bar_index,
                "exit_reason": x.exit.reason,
                "return": r,
                "win": r > 0,
            }
        )
    return rows


def summarize(rows):
    if not rows:
        return {"trades": 0}
    rets = [r["return"] for r in rows]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    gross_loss = -sum(losses)
    return {
        "trades": len(rets),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(rets),
        "total_return": sum(rets),
        "compound_return": __import__("math").prod(1 + r for r in rets) - 1,
        "profit_factor": sum(wins) / gross_loss if gross_loss else float("inf"),
        "avg_sequence_bars": sum(r["sequence_bars"] for r in rows) / len(rows),
        "avg_sweep_to_mss": sum(r["sweep_to_mss"] for r in rows) / len(rows),
        "avg_mss_to_fvg": sum(r["mss_to_fvg"] for r in rows) / len(rows),
        "avg_fvg_to_retest": sum(r["fvg_to_retest"] for r in rows) / len(rows),
    }


def bucket_rows(rows):
    """Describe whether sequence timing contains a simple outcome signal.

    Buckets are fixed, non-optimized descriptive bins. They are not used to
    choose parameters or claim an edge.
    """
    buckets = defaultdict(list)
    for r in rows:
        # Fixed structural buckets in bars, chosen before looking at outcomes.
        speed = "fast" if r["sequence_bars"] <= 8 else "slow"
        retest = "quick_retest" if r["fvg_to_retest"] <= 4 else "delayed_retest"
        buckets[(r["direction"], speed, retest)].append(r)
    return buckets


def main():
    bars = load_bars()
    events = ReferenceStrategy().process(bars)
    ledger = build_ledger(events)
    exit_policy = FixedRiskRewardExit(0.01, 2.0)
    windows = generate_walk_forward(len(bars), TRAIN, TEST, STEP)

    all_oos = []
    for n, w in enumerate(windows):
        test_ledger = [
            t for t in ledger if w.test_start <= t.entry_bar < w.test_end
        ]
        executed, skipped = execute_trades(
            bars, test_ledger, exit_policy, max_concurrent=1
        )
        rows = outcome(executed)
        all_oos.extend(rows)

        print(f"WINDOW {n} EXECUTED {len(executed)} SKIPPED_OVERLAP {skipped}")
        for d in ("bullish", "bearish"):
            group = [r for r in rows if r["direction"] == d]
            print(d.upper(), summarize(group))
        print("TRADE_SEQUENCE_ROWS")
        for r in rows:
            print(r)

        print("FIXED_SEQUENCE_BUCKETS")
        for key, group in sorted(bucket_rows(rows).items()):
            print(key, summarize(group))

    print("ALL_OOS", summarize(all_oos))
    print("ALL_OOS_FIXED_BUCKETS")
    for key, group in sorted(bucket_rows(all_oos).items()):
        print(key, summarize(group))


if __name__ == "__main__":
    main()
