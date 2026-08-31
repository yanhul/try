"""Audit ledger sequence semantics against the reference strategy contract."""
from engine.backtest import load_bars
from engine.events import EventType
from engine.ledger import build_ledger
from engine.strategy import ReferenceStrategy

bars = load_bars("data/BTCUSDT_1h.csv")
events = ReferenceStrategy().process(bars)
ledger = build_ledger(events)
by_key = {(e.bar_index, e.direction, e.event_type): e for e in events}
bad = []

for t in ledger:
    if not (0 <= t.sweep_bar <= t.mss_bar <= t.fvg_bar < t.entry_bar < len(bars)):
        bad.append((t, "non-increasing or out-of-range bars"))
        continue
    checks = [
        (t.sweep_bar, EventType.LIQUIDITY_SWEEP),
        (t.mss_bar, EventType.MSS),
        (t.fvg_bar, EventType.FVG),
        (t.entry_bar, EventType.RETEST),
    ]
    for bar, typ in checks:
        if (bar, t.direction, typ) not in by_key:
            bad.append((t, f"missing {typ.value} at bar {bar}"))

print("EVENTS:", len(events))
print("LEDGER:", len(ledger))
print("BAD:", len(bad))
for item in bad[:10]:
    print(item)
raise SystemExit(1 if bad else 0)
