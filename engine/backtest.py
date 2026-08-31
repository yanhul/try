import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from .events import MarketBar
from .strategy import ReferenceStrategy


REQUIRED_COLUMNS = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def parse_timestamp(value: str) -> datetime:
    value = value.strip()

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    ts = datetime.fromisoformat(value)

    if ts.tzinfo is None:
        raise ValueError("timestamp must contain timezone information")

    return ts.astimezone(timezone.utc)


def load_bars(path: str | Path) -> list[MarketBar]:
    path = Path(path)

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns

        if missing:
            raise ValueError(
                "missing required columns: "
                + ", ".join(sorted(missing))
            )

        bars: list[MarketBar] = []
        previous_timestamp: datetime | None = None

        for row_number, row in enumerate(reader, start=2):
            try:
                timestamp = parse_timestamp(row["timestamp"])

                values = {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
                if not all(math.isfinite(v) for v in values.values()):
                    raise ValueError("non-finite OHLCV value")
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"invalid OHLCV at CSV row {row_number}"
                ) from exc

            if (
                values["open"] <= 0
                or values["high"] <= 0
                or values["low"] <= 0
                or values["close"] <= 0
            ):
                raise ValueError(
                    f"non-positive OHLC at CSV row {row_number}"
                )

            if values["volume"] < 0:
                raise ValueError(
                    f"negative volume at CSV row {row_number}"
                )

            if values["high"] < max(
                values["open"],
                values["close"],
                values["low"],
            ):
                raise ValueError(
                    f"invalid high at CSV row {row_number}"
                )

            if values["low"] > min(
                values["open"],
                values["close"],
                values["high"],
            ):
                raise ValueError(
                    f"invalid low at CSV row {row_number}"
                )

            if (
                previous_timestamp is not None
                and timestamp <= previous_timestamp
            ):
                raise ValueError(
                    f"timestamps must be strictly increasing at "
                    f"CSV row {row_number}"
                )

            bars.append(
                MarketBar(
                    timestamp=timestamp,
                    open=values["open"],
                    high=values["high"],
                    low=values["low"],
                    close=values["close"],
                    volume=values["volume"],
                )
            )

            previous_timestamp = timestamp

    return bars


def event_to_dict(event):
    return {
        "timestamp": event.timestamp.isoformat(),
        "bar_index": event.bar_index,
        "event_type": event.event_type.value,
        "direction": event.direction.value,
        "price": event.price,
    }


def run_backtest(data_path: str | Path) -> dict:
    bars = load_bars(data_path)
    events = ReferenceStrategy().process(bars)

    return {
        "schema_version": 1,
        "data": {
            "file": str(Path(data_path).resolve()),
            "bars": len(bars),
            "start": bars[0].timestamp.isoformat() if bars else None,
            "end": bars[-1].timestamp.isoformat() if bars else None,
        },
        "strategy": {
            "name": "ReferenceStrategy",
            "mode": "event_reference",
        },
        "events": [event_to_dict(event) for event in events],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the deterministic OHLCV reference event engine."
    )
    parser.add_argument("csv_file")
    parser.add_argument("--out", required=True)

    args = parser.parse_args()

    result = run_backtest(args.csv_file)

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print(
        f"PASS: {result['data']['bars']} bars, "
        f"{len(result['events'])} events -> {output}"
    )


if __name__ == "__main__":
    main()
