from datetime import datetime, timedelta, timezone

from engine.split_research import run_split_research


def test_split_research(tmp_path):
    csv = tmp_path / "data.csv"

    rows = ["timestamp,open,high,low,close,volume"]

    for i in range(30):
        price = 100 + i
        rows.append(
            f"2026-01-{i+1:02d}T00:00:00Z,"
            f"{price},{price+1},{price-1},{price},10"
        )

    csv.write_text("\n".join(rows), encoding="utf-8")

    result = run_split_research(csv, tmp_path / "result.json")

    assert result["dataset_bars"] == 30
    assert set(result["splits"]) == {"IS", "VALIDATION", "OOS"}

    assert result["splits"]["IS"]["bars"] == 18
    assert result["splits"]["VALIDATION"]["bars"] == 6
    assert result["splits"]["OOS"]["bars"] == 6


def test_split_research_parameters_are_applied(tmp_path):
    csv = tmp_path / "data.csv"
    rows = ["timestamp,open,high,low,close,volume"]
    for i in range(60):
        price = 100 + (i % 12) * 2
        rows.append(
            f"{(datetime(2026, 2, 1, tzinfo=timezone.utc) + timedelta(hours=i)).isoformat().replace("+00:00", "Z")},"
            f"{price},{price+3},{price-3},{price},10"
        )
    csv.write_text("\n".join(rows), encoding="utf-8")

    result = run_split_research(
        csv, tmp_path / "result.json", stop_fraction=0.02, reward_multiple=1.0
    )

    assert result["parameters"] == {
        "stop_fraction": 0.02,
        "reward_multiple": 1.0,
    }
