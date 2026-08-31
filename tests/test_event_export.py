from engine.event_export import export_events


def test_event_export(tmp_path):
    data = tmp_path / "data.csv"
    output = tmp_path / "events.csv"

    data.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-01-01T00:00:00Z,100,105,95,100,10\n"
        "2026-01-01T00:01:00Z,100,103,94,97,11\n",
        encoding="utf-8",
    )

    count = export_events(data, output)

    assert count == 1

    lines = output.read_text(encoding="utf-8").splitlines()

    assert lines[0] == (
        "timestamp,bar_index,event_type,direction,price"
    )

    assert "LIQUIDITY_SWEEP" in lines[1]
    assert "bullish" in lines[1]
