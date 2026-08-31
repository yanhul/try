from pathlib import Path

from engine.wf_runner import run_walk_forward


DATA = Path("data/BTCUSDT_1h.csv")
OUTPUT = Path("research/BTCUSDT_1h_wf_research_grade_v1.json")


if __name__ == "__main__":
    result = run_walk_forward(
        DATA,
        OUTPUT,
        train_size=1100,
        test_size=500,
        step=500,
        stop_fraction=0.01,
        reward_multiple=2.0,
        research_grade=True,
    )
    print(
        f"PASS: {result['window_count']} research-grade windows -> {OUTPUT}"
    )
