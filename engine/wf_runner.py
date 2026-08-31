from pathlib import Path
import json

from .backtest import load_bars
from .walk_forward import generate_walk_forward
from .split_research import run_split
from .evaluation import validate_walk_forward_evidence


def run_walk_forward(
    csv_path,
    output_path,
    train_size,
    test_size,
    step=None,
    stop_fraction=0.01,
    reward_multiple=2.0,
    research_grade=True,
):
    bars = load_bars(csv_path)

    windows = generate_walk_forward(
        len(bars),
        train_size,
        test_size,
        step,
    )

    effective_step = test_size if step is None else step
    if research_grade:
        validate_walk_forward_evidence(
            dataset_bars=len(bars),
            train_size=train_size,
            test_size=test_size,
            step=effective_step,
            window_count=len(windows),
        )

    results = []

    for index, window in enumerate(windows):
        results.append(
            {
                "window": index,
                "train": run_split(
                    bars,
                    window.train_start,
                    window.train_end,
                    stop_fraction,
                    reward_multiple,
                ),
                "test": run_split(
                    bars,
                    window.test_start,
                    window.test_end,
                    stop_fraction,
                    reward_multiple,
                ),
            }
        )

    result = {
        "schema_version": 2,
        "dataset_bars": len(bars),
        "parameters": {
            "train_size": train_size,
            "test_size": test_size,
            "step": effective_step,
            "stop_fraction": stop_fraction,
            "reward_multiple": reward_multiple,
            "research_grade": research_grade,
        },
        "window_count": len(results),
        "windows": results,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    return result
