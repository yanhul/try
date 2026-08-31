from __future__ import annotations
import csv
from collections import defaultdict
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
        es=sorted((e for e in events if w.test_start<=e.bar_index<w.test_end),key=lambda e:e.bar_index)
        sweeps=[e for e in es if e.event_type==EventType.LIQUIDITY_SWEEP]; mss=[e for e in es if e.event_type==EventType.MSS]; fvgs=[e for e in es if e.event_type==EventType.FVG]; rets=[e for e in es if e.event_type==EventType.RETEST]
        rows=[]
        for s in sweeps:
            ms=next((x for x in mss if x.bar_index>s.bar_index and x.direction==s.direction and x.bar_index-s.bar_index<=50),None)
            if not ms: continue
            f=next((x for x in fvgs if x.bar_index>ms.bar_index and x.direction==ms.direction and x.bar_index-ms.bar_index<=20),None)
            if not f: continue
            r=next((x for x in rets if x.bar_index>f.bar_index and x.direction==f.direction and x.bar_index-f.bar_index<=50),None)
            if r: rows.append(r)
        print('WINDOW',n)
        for d in ('bullish','bearish'):
            rs=[r for r in rows if r.direction.value==d]
            print(d.upper(),'FULL_SEQUENCE',len(rs),'RETEST_BARS',[r.bar_index for r in rs])

if __name__=='__main__': main()
