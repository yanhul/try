from engine.backtest import load_bars
from engine.events import EventType
from engine.strategy import ReferenceStrategy

bars = load_bars("data/BTCUSDT_1h.csv")
events = ReferenceStrategy().process(bars)
sweeps = [e for e in events if e.event_type == EventType.LIQUIDITY_SWEEP]
mss = [e for e in events if e.event_type == EventType.MSS]
sweep_bars = {e.bar_index for e in sweeps}
mss_bars = {e.bar_index for e in mss}
same = sorted(sweep_bars & mss_bars)
print(f"BARS {len(bars)}")
print(f"SWEEP_EVENTS {len(sweeps)}")
print(f"MSS_EVENTS {len(mss)}")
print(f"SAME_BAR_UNIQUE {len(same)}")
print("SAME_BAR_INDEXES", same)
