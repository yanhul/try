import json
from datetime import datetime, timedelta, timezone

from engine.research_run import run_research


def test_research_run(tmp_path):
    csv = tmp_path / "data.csv"

    rows = [
        "timestamp,open,high,low,close,volume",
        "2026-01-01T00:00:00Z,100,105,95,100,10",
        "2026-01-01T01:00:00Z,100,103,94,97,10",
        "2026-01-01T02:00:00Z,97,104,96,103,10",
        "2026-01-01T03:00:00Z,103,110,102,108,10",
        "2026-01-01T04:00:00Z,108,109,106,107,10",
    ]

    csv.write_text("\n".join(rows), encoding="utf-8")

    output = tmp_path / "result.json"
    result = run_research(csv, output)

    assert result["bars"] == 5
    assert result["events"] >= 0
    assert result["ledger_trades"] >= 0
    assert result["evaluated_trades"] >= 0

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["bars"] == 5


def test_research_parameters_are_applied(tmp_path):
    csv = tmp_path / "data.csv"
    rows = ["timestamp,open,high,low,close,volume"]
    for i in range(80):
        price = 100 + (i % 10) * 2
        rows.append(
            f"{(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)).isoformat().replace("+00:00", "Z")},"
            f"{price},{price+3},{price-3},{price},10"
        )
    csv.write_text("\n".join(rows), encoding="utf-8")

    from engine.research_run import run_research
    result = run_research(csv, tmp_path / "result.json", 0.02, 1.0)

    assert result["parameters"] == {
        "stop_fraction": 0.02,
        "reward_multiple": 1.0,
    }
