from collections import Counter
from engine.backtest import load_bars
from engine.ledger import build_ledger
from engine.strategy import ReferenceStrategy

bars = load_bars("data/BTCUSDT_1h.csv")
events = ReferenceStrategy().process(bars)
ledger = build_ledger(events)

print("TRADES:", len(ledger))
print("DIRECTION:", Counter(t.direction.value for t in ledger))

print("\nSEQUENCE DELAYS")
for direction in ("bullish", "bearish"):
    rows = [t for t in ledger if t.direction.value == direction]

    sweep_mss = [t.mss_bar - t.sweep_bar for t in rows]
    mss_fvg = [t.fvg_bar - t.mss_bar for t in rows]
    fvg_entry = [t.entry_bar - t.fvg_bar for t in rows]

    print(direction)
    print("  trades:", len(rows))
    print("  sweep->mss:", sweep_mss)
    print("  mss->fvg:", mss_fvg)
    print("  fvg->entry:", fvg_entry)
