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
BOOTSTRAP_REPS = 10000
BLOCK_SIZE = 3
SEED = 20260831


def load_bars():
    with open(DATA, newline="", encoding="utf-8-sig") as f:
        return [MarketBar(timestamp=r["timestamp"], open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"])) for r in csv.DictReader(f)]


def trade_returns():
    bars = load_bars()
    events = ReferenceStrategy().process(bars)
    ledger = build_ledger(events)
    exit_policy = FixedRiskRewardExit(0.01, 2.0)
    windows = generate_walk_forward(len(bars), TRAIN, TEST, STEP)
    rows = []
    for w in windows:
        test_ledger = [t for t in ledger if w.test_start <= t.entry_bar < w.test_end]
        executed, _ = execute_trades(bars, test_ledger, exit_policy, max_concurrent=1)
        for x in executed:
            t = x.ledger_trade
            e, p = t.entry_price, x.exit.price
            r = (p / e - 1.0) if t.direction.value == "bullish" else (e / p - 1.0)
            rows.append((x.exit.bar_index, r))
    return [r for _, r in sorted(rows)]


def compound(rs):
    return math.prod(1.0 + r for r in rs) - 1.0


def block_sample(rs, rng):
    n = len(rs)
    if n <= BLOCK_SIZE:
        return [rng.choice(rs) for _ in range(n)]
    blocks = [rs[i:i + BLOCK_SIZE] for i in range(0, n - BLOCK_SIZE + 1)]
    out = []
    while len(out) < n:
        out.extend(rng.choice(blocks))
    return out[:n]


def percentile(xs, q):
    ys = sorted(xs)
    pos = (len(ys) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return ys[lo]
    return ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)


def main():
    rs = trade_returns()
    observed_total = sum(rs)
    observed_compound = compound(rs)
    rng = random.Random(SEED)
    totals, compounds = [], []
    for _ in range(BOOTSTRAP_REPS):
        sample = block_sample(rs, rng)
        totals.append(sum(sample))
        compounds.append(compound(sample))
    print("ROBUSTNESS_CONFIG", {"bootstrap_reps": BOOTSTRAP_REPS, "block_size": BLOCK_SIZE, "seed": SEED, "train": TRAIN, "test": TEST, "step": STEP, "exit_stop": 0.01, "exit_target": 2.0})
    print("OBSERVED_OOS", {"trades": len(rs), "total_return": observed_total, "compound_return": observed_compound, "mean_trade_return": sum(rs) / len(rs)})
    print("BLOCK_BOOTSTRAP_95", {"total_ci_95": (percentile(totals, .025), percentile(totals, .975)), "compound_ci_95": (percentile(compounds, .025), percentile(compounds, .975)), "p_boot_total_positive": sum(x > 0 for x in totals) / len(totals)})
    print("INTERPRETATION_RULES", {"total_ci_crosses_zero": percentile(totals, .025) <= 0 <= percentile(totals, .975), "compound_ci_crosses_zero": percentile(compounds, .025) <= 0 <= percentile(compounds, .975)})


if __name__ == "__main__":
    main()
