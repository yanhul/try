"""OOS robustness audit using fixed walk-forward trades.

This is a descriptive robustness check only. It does not optimize strategy
parameters, alter engine behavior, or use resampled outcomes to select a rule.

Outputs:
- observed OOS trade count / return / compound return / profit factor
- IID bootstrap percentile intervals for total and compound return
- bootstrap probability that total return is positive
- sign-permutation Monte Carlo p-value for mean trade return > 0
- per-window observed returns, so instability is visible rather than hidden

The bootstrap resamples realized OOS trades with replacement. The sign
permutation keeps each trade's absolute return fixed and randomly flips its
sign; this is a simple null test for positive directional payoff, not a claim
of independent financial observations.
"""

from __future__ import annotations

import csv
import math
import random
from statistics import mean

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

BOOTSTRAP_REPS = 10_000
PERMUTATION_REPS = 10_000
SEED = 20260831


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


def trade_return(executed):
    rows = []
    for x in executed:
        t = x.ledger_trade
        e = t.entry_price
        p = x.exit.price
        d = t.direction.value
        r = (p / e - 1.0) if d == "bullish" else (e / p - 1.0)
        rows.append(r)
    return rows


def summarize(returns):
    if not returns:
        return {"trades": 0}
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    gross_loss = -sum(losses)
    return {
        "trades": len(returns),
        "total_return": sum(returns),
        "compound_return": math.prod(1.0 + r for r in returns) - 1.0,
        "mean_trade_return": mean(returns),
        "win_rate": len(wins) / len(returns),
        "profit_factor": sum(wins) / gross_loss if gross_loss else float("inf"),
    }


def percentile(sorted_values, q):
    if not sorted_values:
        raise ValueError("cannot calculate percentile of empty sample")
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def bootstrap(returns, reps, rng):
    n = len(returns)
    total_samples = []
    compound_samples = []
    positive_total = 0
    for _ in range(reps):
        sample = [returns[rng.randrange(n)] for _ in range(n)]
        total = sum(sample)
        compound = math.prod(1.0 + r for r in sample) - 1.0
        total_samples.append(total)
        compound_samples.append(compound)
        if total > 0:
            positive_total += 1
    total_samples.sort()
    compound_samples.sort()
    return {
        "total_ci_95": (
            percentile(total_samples, 0.025),
            percentile(total_samples, 0.975),
        ),
        "compound_ci_95": (
            percentile(compound_samples, 0.025),
            percentile(compound_samples, 0.975),
        ),
        "p_boot_total_positive": positive_total / reps,
    }


def sign_permutation(returns, reps, rng):
    """Monte Carlo one-sided sign-flip null: E[return] <= 0."""
    observed = sum(returns) / len(returns)
    extreme = 0
    for _ in range(reps):
        total = 0.0
        for r in returns:
            total += r if rng.getrandbits(1) else -r
        if total / len(returns) >= observed:
            extreme += 1
    # +1 correction avoids a reported zero Monte Carlo p-value.
    return (extreme + 1) / (reps + 1)


def collect_oos():
    bars = load_bars()
    events = ReferenceStrategy().process(bars)
    ledger = build_ledger(events)
    exit_policy = FixedRiskRewardExit(0.01, 2.0)
    windows = generate_walk_forward(len(bars), TRAIN, TEST, STEP)

    all_returns = []
    window_returns = []
    for n, w in enumerate(windows):
        test_ledger = [
            t for t in ledger if w.test_start <= t.entry_bar < w.test_end
        ]
        executed, skipped = execute_trades(
            bars, test_ledger, exit_policy, max_concurrent=1
        )
        returns = trade_return(executed)
        all_returns.extend(returns)
        window_returns.append((n, returns, skipped))
    return all_returns, window_returns


def main():
    returns, window_returns = collect_oos()
    observed = summarize(returns)

    bootstrap_result = bootstrap(
        returns, BOOTSTRAP_REPS, random.Random(SEED)
    )
    permutation_p = sign_permutation(
        returns, PERMUTATION_REPS, random.Random(SEED + 1)
    )

    print("ROBUSTNESS_CONFIG", {
        "bootstrap_reps": BOOTSTRAP_REPS,
        "permutation_reps": PERMUTATION_REPS,
        "seed": SEED,
        "train": TRAIN,
        "test": TEST,
        "step": STEP,
        "exit_stop": 0.01,
        "exit_target": 2.0,
    })
    print("OBSERVED_OOS", observed)
    print("BOOTSTRAP_95", bootstrap_result)
    print("SIGN_PERMUTATION_P_ONE_SIDED", permutation_p)

    print("WINDOW_RETURNS")
    for n, window, skipped in window_returns:
        print(n, summarize(window), "SKIPPED_OVERLAP", skipped)

    print("INTERPRETATION_RULES")
    print("BOOTSTRAP_CI_CROSSES_ZERO", bootstrap_result["total_ci_95"][0] <= 0 <= bootstrap_result["total_ci_95"][1])
    print("PERMUTATION_SIGNIFICANT_AT_5PCT", permutation_p < 0.05)


if __name__ == "__main__":
    main()
