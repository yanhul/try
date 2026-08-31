import json
from pathlib import Path

from engine.split_research import run_split

from engine.backtest import load_bars
from engine.data_split import chronological_split, validate_splits

bars = load_bars("data/BTCUSDT_1h.csv")
splits = chronological_split(len(bars))
validate_splits(splits, len(bars))

results = []

for stop in [0.005, 0.01, 0.015, 0.02]:
    for rr in [1.0, 1.5, 2.0, 2.5, 3.0]:
        row = {
            "stop_fraction": stop,
            "reward_multiple": rr,
            "IS": run_split(bars, splits[0].start, splits[0].end, stop, rr),
            "VALIDATION": run_split(bars, splits[1].start, splits[1].end, stop, rr),
        }
        results.append(row)

Path("research").mkdir(exist_ok=True)
Path("research/BTCUSDT_1h_grid.json").write_text(
    json.dumps(
        {
            "dataset_bars": len(bars),
            "experiment_count": len(results),
            "experiments": results,
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("EXPERIMENTS:", len(results))
