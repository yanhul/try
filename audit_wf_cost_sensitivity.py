from __future__ import annotations

from engine.backtest import load_bars
from engine.split_research import run_split
from engine.walk_forward import generate_walk_forward


SCENARIOS = (
    ("zero_cost", 0.0),
    ("10bp_round_trip", 0.001),
    ("20bp_round_trip", 0.002),
)


if __name__ == "__main__":
    bars = load_bars("data/BTCUSDT_1h.csv")
    windows = generate_walk_forward(len(bars), 1100, 500, 500)

    for name, cost in SCENARIOS:
        print("SCENARIO", name, "ROUND_TRIP_COST", cost)
        total_return = 1.0
        for i, w in enumerate(windows):
            result = run_split(
                bars,
                w.test_start,
                w.test_end,
                0.01,
                2.0,
                cost,
            )
            m = result["metrics"]
            total_return *= 1.0 + m["total_return"]
            print(
                "WINDOW", i,
                "TRADES", result["trades"],
                "RETURN", m["total_return"],
                "PF", m["profit_factor"],
                "WIN_RATE", m["win_rate"],
                "MAX_DD", m["max_drawdown"],
            )
        print("COMPOUNDED_OOS_RETURN", total_return - 1.0)
