import csv
from pathlib import Path

import pytest

from engine.data_validator import main


def write_csv(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["timestamp", "open", "high", "low", "close", "volume"]
        )
        w.writerows(rows)


def base_rows():
    return [
        [
            f"2026-01-01T00:{i:02d}:00+00:00",
            "100",
            "101",
            "99",
            "100",
            "10",
        ]
        for i in range(10)
    ]


def test_nan_rejected(tmp_path, monkeypatch):
    rows = base_rows()
    rows[3][1] = "nan"

    p = tmp_path / "bad.csv"
    write_csv(p, rows)

    monkeypatch.setattr(
        "sys.argv",
        ["data_validator", str(p)]
    )

    with pytest.raises(SystemExit, match="NaN/Inf"):
        main()


def test_gap_rejected(tmp_path, monkeypatch):
    rows = base_rows()
    rows[5][0] = "2026-01-01T00:06:00+00:00"

    p = tmp_path / "gap.csv"
    write_csv(p, rows)

    monkeypatch.setattr(
        "sys.argv",
        [
            "data_validator",
            str(p),
            "--interval-seconds",
            "60",
        ],
    )

    with pytest.raises(SystemExit, match="gap/cadence"):
        main()


def test_valid_dataset(tmp_path, monkeypatch, capsys):
    rows = base_rows()

    # Make timestamps genuinely one minute apart.
    from datetime import datetime, timedelta, timezone

    start = datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )

    for i, row in enumerate(rows):
        row[0] = (
            start + timedelta(minutes=i)
        ).isoformat()

    p = tmp_path / "good.csv"
    write_csv(p, rows)

    monkeypatch.setattr(
        "sys.argv",
        [
            "data_validator",
            str(p),
            "--interval-seconds",
            "60",
        ],
    )

    main()

    assert "PASS: 10 candles validated" in capsys.readouterr().out
