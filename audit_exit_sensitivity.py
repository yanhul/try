from __future__ import annotations

from engine.backtest import load_bars
from engine.split_research import run_split
from engine.walk_forward import generate_walk_forward


# Fixed, descriptive grid declared in source before reading OOS results.
# The incumbent (1% stop, 2R target) is included as the reference row.
# This audit does not select or modify the strategy.
STOP_GRID = (0.005, 0.01, 0.015)
REWARD_GRID = (1.5, 2.0, 2.5)
ROUND_TRIP_COST = 0.0
TRAIN = 1100
TEST = 500
STEP = 500
INCUMBENT = (0.01, 2.0)


def metrics_for(bars, windows, stop_fraction, reward_multiple):
    compounded = 1.0
    rows = []
    total_trades = 0
    for i, w in enumerate(windows):
        result = run_split(
            bars,
            w.test_start,
            w.test_end,
            stop_fraction,
            reward_multiple,
            ROUND_TRIP_COST,
        )
        m = result["metrics"]
        compounded *= 1.0 + m["total_return"]
        total_trades += result["trades"]
        rows.append(
            {
                "window": i,
                "trades": result["trades"],
                "return": m["total_return"],
                "compound_return": m["compound_return"],
                "win_rate": m["win_rate"],
                "profit_factor": m["profit_factor"],
                "max_drawdown": m["max_drawdown"],
                "skipped_overlap": result["skipped_overlap_trades"],
            }
        )
    return total_trades, compounded - 1.0, rows


if __name__ == "__main__":
    bars = load_bars("data/BTCUSDT_1h.csv")
    windows = generate_walk_forward(len(bars), TRAIN, TEST, STEP)

    print(
        "SENSITIVITY_CONFIG",
        {
            "stop_grid": STOP_GRID,
            "reward_grid": REWARD_GRID,
            "round_trip_cost": ROUND_TRIP_COST,
            "train": TRAIN,
            "test": TEST,
            "step": STEP,
            "incumbent": INCUMBENT,
        },
    )

    for stop_fraction in STOP_GRID:
        for reward_multiple in REWARD_GRID:
            trades, compounded, rows = metrics_for(
                bars, windows, stop_fraction, reward_multiple
            )
            print(
                "CONFIG",
                {"stop_fraction": stop_fraction, "reward_multiple": reward_multiple},
                "TRADES",
                trades,
                "COMPOUNDED_OOS_RETURN",
                compounded,
            )
            for row in rows:
                print("WINDOW", row)

    print("INCUMBENT", {"stop_fraction": INCUMBENT[0], "reward_multiple": INCUMBENT[1]})
    print("DECISION", "DESCRIPTIVE_ONLY_NO_SELECTION")
