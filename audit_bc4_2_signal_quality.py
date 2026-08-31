from __future__ import annotations

import csv
from collections import defaultdict

from engine.events import MarketBar, Direction
from engine.strategy import ReferenceStrategy
from engine.ledger import build_ledger
from engine.execution import execute_trades
from engine.risk_exit import FixedRiskRewardExit
from engine.walk_forward import generate_walk_forward

DATA = "data/BTCUSDT_1h.csv"
TRAIN, TEST, STEP = 1100, 500, 500
STOP, TARGET = 0.01, 2.0
OOS_START, OOS_END = 2899, 3624


def load_bars():
    with open(DATA, newline="", encoding="utf-8-sig") as f:
        return [
            MarketBar(
                timestamp=r["timestamp"],
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["volume"]),
            )
            for r in csv.DictReader(f)
        ]


def close_location(bar: MarketBar, direction: Direction) -> float:
    rng = bar.high - bar.low
    if rng <= 0:
        return 0.5
    if direction == Direction.BULLISH:
        return (bar.close - bar.low) / rng
    return (bar.high - bar.close) / rng


def signed_body(bar: MarketBar, direction: Direction) -> float:
    rng = bar.high - bar.low
    if rng <= 0:
        return 0.0
    body = bar.close - bar.open
    return (body / rng) if direction == Direction.BULLISH else (-body / rng)


def summarize(rows):
    if not rows:
        return {"n": 0}
    wins = [r for r in rows if r["return"] > 0]
    losses = [r for r in rows if r["return"] < 0]
    gross_win = sum(r["return"] for r in wins)
    gross_loss = -sum(r["return"] for r in losses)
    return {
        "n": len(rows),
        "total_return": sum(r["return"] for r in rows),
        "avg_return": sum(r["return"] for r in rows) / len(rows),
        "win_rate": len(wins) / len(rows),
        "profit_factor": (gross_win / gross_loss) if gross_loss else None,
        "stop_rate": sum(r["reason"].startswith("stop") for r in rows) / len(rows),
    }


def diagnostic_for_split(bars, start, end, events):
    es = [e for e in events if start <= e.bar_index < end]
    ledger = build_ledger(es)
    executed, skipped = execute_trades(
        bars, ledger, FixedRiskRewardExit(STOP, TARGET), max_concurrent=1
    )

    rows = []
    for x in executed:
        t = x.ledger_trade
        entry = bars[t.entry_bar]
        sweep = bars[t.sweep_bar]
        rows.append(
            {
                "direction": t.direction.value,
                "return": (
                    (x.exit.price / t.entry_price - 1.0)
                    if t.direction == Direction.BULLISH
                    else (t.entry_price / x.exit.price - 1.0)
                ),
                "reason": x.exit.reason,
                "entry_close_location": close_location(entry, t.direction),
                "entry_signed_body": signed_body(entry, t.direction),
                "sweep_close_location": close_location(sweep, t.direction),
                "sweep_signed_body": signed_body(sweep, t.direction),
                "sweep_to_entry": t.entry_bar - t.sweep_bar,
                "mss_to_entry": t.entry_bar - t.mss_bar,
                "fvg_to_entry": t.entry_bar - t.fvg_bar,
            }
        )

    print("SPLIT", start, end, {"executed": len(rows), "skipped_overlap": skipped})
    print("OVERALL", summarize(rows))

    # Fixed, direction-neutral diagnostic cuts. These are not optimized and
    # are not used for strategy selection. Thresholds are structural midpoints
    # or small integer lags, applied identically to every split.
    specs = [
        ("entry_close_location", lambda r: r["entry_close_location"] >= 0.5),
        ("entry_signed_body", lambda r: r["entry_signed_body"] >= 0.0),
        ("sweep_close_location", lambda r: r["sweep_close_location"] >= 0.5),
        ("sweep_signed_body", lambda r: r["sweep_signed_body"] >= 0.0),
        ("fast_entry_le_1bar", lambda r: r["sweep_to_entry"] <= 1),
        ("fast_entry_le_2bar", lambda r: r["sweep_to_entry"] <= 2),
        ("fast_entry_le_3bar", lambda r: r["sweep_to_entry"] <= 3),
    ]
    for name, predicate in specs:
        a = [r for r in rows if predicate(r)]
        b = [r for r in rows if not predicate(r)]
        print("FEATURE", name, "PASS", summarize(a), "FAIL", summarize(b))


def main():
    bars = load_bars()
    events = ReferenceStrategy().process(bars)
    print(
        "BC4_2_STATUS",
        {
            "purpose": "failure_analysis_only",
            "single_change": None,
            "selection": False,
            "oos_touched": False,
            "oos_reserved": (OOS_START, OOS_END),
        },
    )
    for n, w in enumerate(generate_walk_forward(len(bars), TRAIN, TEST, STEP)):
        # Only IS and validation are inspected. The reserved future OOS range
        # is deliberately excluded from this diagnostic.
        if w.test_end <= OOS_START:
            label = "IS" if n == 0 else "VALIDATION"
            print("SPLIT_LABEL", label, n)
            diagnostic_for_split(bars, w.test_start, w.test_end, events)
    print(
        "CAUSE_RULE",
        "A feature may justify a future single-change hypothesis only if its fixed diagnostic separation is directionally repeatable across IS and validation; no OOS selection.",
    )


if __name__ == "__main__":
    main()
