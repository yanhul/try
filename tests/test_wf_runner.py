from datetime import datetime, timedelta, timezone

from engine.wf_runner import run_walk_forward


def test_wf_runner(tmp_path):
    csv = tmp_path / "data.csv"

    rows = ["timestamp,open,high,low,close,volume"]

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for i in range(40):
        ts = start + timedelta(hours=i)
        p = 100 + i
        rows.append(
            f"{ts.isoformat()},{p},{p+1},{p-1},{p},10"
        )

    csv.write_text("\n".join(rows), encoding="utf-8")

    result = run_walk_forward(
        csv,
        tmp_path / "wf.json",
        train_size=20,
        test_size=10,
        step=10,
        research_grade=False,
    )

    assert result["dataset_bars"] == 40
    assert result["window_count"] == 2
    assert result["parameters"]["research_grade"] is False
