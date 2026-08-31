from __future__ import annotations

import csv
from dataclasses import dataclass

from engine.events import MarketBar
from engine.strategy import ReferenceStrategy


@dataclass(frozen=True)
class Result:
    events: int
    sweeps: int
    mss: int
    fvg: int
    retests: int


def load_bars(path: str) -> list[MarketBar]:
    bars = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            bars.append(
                MarketBar(
                    timestamp=r["timestamp"],
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r["volume"]),
                )
            )
    return bars


def run(bars: list[MarketBar], strict: bool) -> Result:
    events = ReferenceStrategy(strict_sequence=strict).process(bars)
    counts = {k: sum(e.event_type.value == k for e in events) for k in ("LIQUIDITY_SWEEP", "MSS", "FVG", "RETEST")}
    return Result(len(events), counts["LIQUIDITY_SWEEP"], counts["MSS"], counts["FVG"], counts["RETEST"])


if __name__ == "__main__":
    bars = load_bars("data/BTCUSDT_1h.csv")
    for strict in (False, True):
        r = run(bars, strict)
        print("STRICT", strict)
        print("EVENTS", r.events)
        print("SWEEP", r.sweeps, "MSS", r.mss, "FVG", r.fvg, "RETEST", r.retests)
