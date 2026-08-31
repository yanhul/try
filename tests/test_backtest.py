import json
from datetime import datetime, timezone

from engine.backtest import load_bars, run_backtest
from engine.events import Direction, EventType


def write_csv(tmp_path, rows):
    path = tmp_path / "data.csv"

    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        + "\n".join(
            ",".join(map(str, row))
            for row in rows
        )
        + "\n",
        encoding="utf-8",
    )

    return path


def test_load_bars_preserves_order(tmp_path):
    path = write_csv(
        tmp_path,
        [
            ("2026-01-01T00:00:00Z", 100, 105, 95, 100, 10),
            ("2026-01-01T00:01:00Z", 100, 103, 94, 97, 11),
        ],
    )

    bars = load_bars(path)

    assert len(bars) == 2
    assert bars[0].timestamp == datetime(
        2026, 1, 1, 0, 0, tzinfo=timezone.utc
    )
    assert bars[1].low == 94


def test_backtest_exports_reference_events(tmp_path):
    path = write_csv(
        tmp_path,
        [
            ("2026-01-01T00:00:00Z", 100, 105, 95, 100, 10),
            ("2026-01-01T00:01:00Z", 100, 103, 94, 97, 11),
        ],
    )

    result = run_backtest(path)

    assert result["schema_version"] == 1
    assert result["data"]["bars"] == 2

    assert len(result["events"]) == 1

    event = result["events"][0]

    assert event["bar_index"] == 1
    assert event["event_type"] == EventType.LIQUIDITY_SWEEP.value
    assert event["direction"] == Direction.BULLISH.value
    assert event["price"] == 95


def test_backtest_has_no_future_event_for_current_bar(tmp_path):
    path = write_csv(
        tmp_path,
        [
            ("2026-01-01T00:00:00Z", 100, 105, 95, 100, 10),
            ("2026-01-01T00:01:00Z", 100, 103, 94, 97, 11),
        ],
    )

    result = run_backtest(path)

    for event in result["events"]:
        assert 0 <= event["bar_index"] < result["data"]["bars"]


def test_backtest_output_is_json_serializable(tmp_path):
    path = write_csv(
        tmp_path,
        [
            ("2026-01-01T00:00:00Z", 100, 105, 95, 100, 10),
            ("2026-01-01T00:01:00Z", 100, 103, 94, 97, 11),
        ],
    )

    result = run_backtest(path)

    encoded = json.dumps(result)
    decoded = json.loads(encoded)

    assert decoded == result
