from __future__ import annotations

import csv
from collections import Counter
from engine.events import MarketBar
from engine.strategy import ReferenceStrategy
from engine.walk_forward import generate_walk_forward

DATA = "data/BTCUSDT_1h.csv"
TRAIN = 1100
TEST = 500
STEP = 500


def load_bars(path: str) -> list[MarketBar]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [MarketBar(timestamp=r["timestamp"], open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"])) for r in csv.DictReader(f)]


def regime(bars: list[MarketBar], start: int, end: int) -> dict:
    xs = bars[start:end]
    returns = [(b.close / a.close - 1.0) for a, b in zip(xs, xs[1:]) if a.close]
    ranges = [(b.high - b.low) / b.close for b in xs if b.close]
    ups = sum(r > 0 for r in returns)
    downs = sum(r < 0 for r in returns)
    return {
        "bars": len(xs),
        "net_return": (xs[-1].close / xs[0].open - 1.0) if xs else 0.0,
        "mean_abs_bar_return": sum(abs(r) for r in returns) / len(returns) if returns else 0.0,
        "mean_range_pct": sum(ranges) / len(ranges) if ranges else 0.0,
        "up_bars": ups,
        "down_bars": downs,
    }


if __name__ == "__main__":
    bars = load_bars(DATA)
    events = ReferenceStrategy().process(bars)
    windows = generate_walk_forward(len(bars), TRAIN, TEST, STEP)
    for n, w in enumerate(windows):
        e = [x for x in events if w.test_start <= x.bar_index < w.test_end]
        c = Counter(x.event_type.value for x in e)
        print("WINDOW", n)
        print("REGIME", regime(bars, w.test_start, w.test_end))
        print("EVENTS", dict(c))
        print("EVENT_DENSITY", len(e) / TEST)
