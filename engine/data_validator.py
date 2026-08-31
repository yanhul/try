#!/usr/bin/env python3

import argparse
import csv
import math
from datetime import datetime, timezone


def parse_timestamp(value: str) -> datetime:
    value = value.strip()

    if not value:
        raise ValueError("empty timestamp")

    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if ts.tzinfo is None:
        raise ValueError("timestamp must include timezone")

    return ts.astimezone(timezone.utc)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv_file")
    p.add_argument(
        "--interval-seconds",
        type=int,
        default=None,
        help="Expected candle interval in seconds. "
             "If supplied, gaps are rejected."
    )
    args = p.parse_args()

    previous = None
    n = 0
    gaps = 0

    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    with open(args.csv_file, newline="", encoding="utf-8") as f:
        rows = csv.DictReader(f)

        if not required.issubset(rows.fieldnames or []):
            raise SystemExit("FAIL: missing columns")

        for line_no, row in enumerate(rows, start=2):
            try:
                ts = parse_timestamp(row["timestamp"])
                o, h, l, c, v = map(
                    float,
                    [
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                    ],
                )
            except Exception as exc:
                raise SystemExit(
                    f"FAIL: invalid row {line_no}: {exc}"
                )

            values = (o, h, l, c, v)

            if not all(math.isfinite(x) for x in values):
                raise SystemExit(
                    f"FAIL: NaN/Inf at row {line_no}: {ts}"
                )

            if min(o, h, l, c) <= 0:
                raise SystemExit(
                    f"FAIL: non-positive OHLC at row {line_no}: {ts}"
                )

            if v < 0:
                raise SystemExit(
                    f"FAIL: negative volume at row {line_no}: {ts}"
                )

            if h < max(o, c, l):
                raise SystemExit(
                    f"FAIL: invalid high at row {line_no}: {ts}"
                )

            if l > min(o, c, h):
                raise SystemExit(
                    f"FAIL: invalid low at row {line_no}: {ts}"
                )

            if previous is not None:
                if ts <= previous:
                    raise SystemExit(
                        f"FAIL: non-increasing timestamp at row "
                        f"{line_no}: {ts}"
                    )

                if args.interval_seconds is not None:
                    delta = (ts - previous).total_seconds()

                    if delta != args.interval_seconds:
                        gaps += 1
                        raise SystemExit(
                            f"FAIL: timestamp gap/cadence mismatch "
                            f"at row {line_no}: "
                            f"expected {args.interval_seconds}s, "
                            f"got {delta}s"
                        )

            previous = ts
            n += 1

    if n < 10:
        raise SystemExit("FAIL: too few rows")

    print(f"PASS: {n} candles validated")


if __name__ == "__main__":
    main()
