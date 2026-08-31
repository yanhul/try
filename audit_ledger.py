from engine.backtest import load_bars
from engine.ledger import build_ledger
from engine.strategy import ReferenceStrategy

bars = load_bars("data/BTCUSDT_1h.csv")
events = ReferenceStrategy().process(bars)
ledger = build_ledger(events)

bad = []

for i, t in enumerate(ledger):
    if not (
        t.sweep_bar <= t.mss_bar
        and t.mss_bar <= t.fvg_bar
        and t.fvg_bar < t.entry_bar
    ):
        bad.append((i, t))

print("EVENTS:", len(events))
print("LEDGER:", len(ledger))
print("BAD_LEDGER:", len(bad))

for item in bad[:20]:
    print(item)
