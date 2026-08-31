from collections import defaultdict
import csv
import math
import random

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
PERMUTATION_REPS = 10000
SEED = 20260831


def load_bars():
    with open(DATA, newline="", encoding="utf-8-sig") as f:
        return [MarketBar(timestamp=r["timestamp"], open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"])) for r in csv.DictReader(f)]


def collect():
    bars = load_bars()
    events = ReferenceStrategy().process(bars)
    ledger = build_ledger(events)
    exit_policy = FixedRiskRewardExit(0.01, 2.0)
    windows = generate_walk_forward(len(bars), TRAIN, TEST, STEP)
    rows = []
    for n, w in enumerate(windows):
        test_ledger = [t for t in ledger if w.test_start <= t.entry_bar < w.test_end]
        executed, skipped = execute_trades(bars, test_ledger, exit_policy, max_concurrent=1)
        for x in executed:
            t = x.ledger_trade
            e, p = t.entry_price, x.exit.price
            r = (p / e - 1.0) if t.direction.value == "bullish" else (e / p - 1.0)
            seq = t.entry_bar - t.sweep_bar
            retest = t.entry_bar - t.fvg_bar
            rows.append({"window": n, "direction": t.direction.value, "return": r, "sequence_bars": seq, "retest_bars": retest})
    return rows


def hypotheses(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[("window", r["window"])].append(r["return"])
        groups[("direction", r["direction"])].append(r["return"])
        speed = "fast" if r["sequence_bars"] <= 8 else "slow"
        retest = "quick_retest" if r["retest_bars"] <= 4 else "delayed_retest"
        groups[("bucket", r["direction"], speed, retest)].append(r["return"])
    return {k: v for k, v in groups.items() if len(v) >= 2}


def statistic(values):
    # Mean return is the fixed descriptive statistic; no parameter selection occurs here.
    return sum(values) / len(values)


def main():
    rows = collect()
    groups = hypotheses(rows)
    observed = {k: statistic(v) for k, v in groups.items()}
    observed_max = max(abs(v) for v in observed.values())

    rng = random.Random(SEED)
    max_stats = []
    # Joint sign permutation preserves every fixed group membership while testing
    # whether the largest observed subgroup mean could arise by chance.
    returns = [r["return"] for r in rows]
    for _ in range(PERMUTATION_REPS):
        signs = [1 if rng.random() < 0.5 else -1 for _ in returns]
        perm_rows = [{**r, "return": r["return"] * signs[i]} for i, r in enumerate(rows)]
        perm_groups = hypotheses(perm_rows)
        max_stats.append(max(abs(statistic(v)) for v in perm_groups.values()))

    adjusted_p = sum(x >= observed_max for x in max_stats) / len(max_stats)
    print("ROBUSTNESS_CONFIG", {"permutation_reps": PERMUTATION_REPS, "seed": SEED, "train": TRAIN, "test": TEST, "step": STEP, "exit_stop": 0.01, "exit_target": 2.0})
    print("HYPOTHESIS_COUNT", len(groups))
    print("OBSERVED_MAX_ABS_MEAN_RETURN", observed_max)
    print("MAXT_PERMUTATION_ADJUSTED_P", adjusted_p)
    print("INTERPRETATION_RULES", {"significant_at_5pct_after_multiple_testing": adjusted_p < 0.05})
    print("OBSERVED_HYPOTHESES")
    for key, value in sorted(observed.items(), key=lambda kv: abs(kv[1]), reverse=True):
        print(key, {"n": len(groups[key]), "mean_return": value})


if __name__ == "__main__":
    main()
