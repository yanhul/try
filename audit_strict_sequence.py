import csv
from engine.events import MarketBar
from engine.strategy import ReferenceStrategy


def load_bars(path: str) -> list[MarketBar]:
    bars = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            bars.append(MarketBar(
                timestamp=row["timestamp"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            ))
    return bars


bars = load_bars("data/BTCUSDT_1h.csv")
for strict in (False, True):
    events = ReferenceStrategy(strict_sequence=strict).process(bars)
    sweeps = [e for e in events if e.event_type.value == "LIQUIDITY_SWEEP"]
    mss = [e for e in events if e.event_type.value == "MSS"]
    fvg = [e for e in events if e.event_type.value == "FVG"]
    retests = [e for e in events if e.event_type.value == "RETEST"]
    same = sum(1 for s in sweeps if any(s.bar_index == m.bar_index for m in mss))
    print("STRICT", strict)
    print("EVENTS", len(events))
    print("SWEEP", len(sweeps), "MSS", len(mss), "FVG", len(fvg), "RETEST", len(retests))
    print("SAME_BAR_SWEEP_MSS", same)
