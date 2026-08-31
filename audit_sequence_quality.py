from __future__ import annotations
import csv
from collections import Counter
from engine.events import MarketBar, EventType
from engine.strategy import ReferenceStrategy
from engine.walk_forward import generate_walk_forward

DATA='data/BTCUSDT_1h.csv'; TRAIN=1100; TEST=500; STEP=500

def load_bars():
    with open(DATA,newline='',encoding='utf-8-sig') as f:
        return [MarketBar(timestamp=r['timestamp'],open=float(r['open']),high=float(r['high']),low=float(r['low']),close=float(r['close']),volume=float(r['volume'])) for r in csv.DictReader(f)]

def main():
    bars=load_bars(); events=ReferenceStrategy().process(bars)
    for n,w in enumerate(generate_walk_forward(len(bars),TRAIN,TEST,STEP)):
        es=[e for e in events if w.test_start<=e.bar_index<w.test_end]
        by={k:[e for e in es if e.event_type==k] for k in EventType}
        sweep_by={e.bar_index:e for e in by[EventType.LIQUIDITY_SWEEP]}
        mss=[e for e in by[EventType.MSS] if e.bar_index in sweep_by]
        fvg=[e for e in by[EventType.FVG]]
        ret=[e for e in by[EventType.RETEST]]
        mss_idx={e.bar_index for e in mss}; fvg_idx={e.bar_index for e in fvg}
        print('WINDOW',n)
        print('SWEEP',len(by[EventType.LIQUIDITY_SWEEP]),'MSS',len(mss),'FVG',len(fvg),'RETEST',len(ret))
        print('SWEEP_TO_MSS',len(mss)/len(sweep_by) if sweep_by else 0)
        print('MSS_TO_FVG',len([e for e in fvg if any(0<e.bar_index-m<10 for m in mss_idx)])/len(mss) if mss else 0)
        print('FVG_TO_RETEST',len([e for e in ret if any(0<e.bar_index-f<50 for f in fvg_idx)])/len(fvg) if fvg else 0)
        print('RETEST_DIRECTIONS',Counter(e.direction.value for e in ret))

if __name__=='__main__': main()
