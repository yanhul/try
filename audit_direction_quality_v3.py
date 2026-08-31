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

def next_match(candidates, start, direction, max_gap):
    for x in candidates:
        if x.bar_index>start and x.direction==direction and x.bar_index-start<=max_gap:
            return x
    return None

def main():
    bars=load_bars(); events=ReferenceStrategy().process(bars)
    for n,w in enumerate(generate_walk_forward(len(bars),TRAIN,TEST,STEP)):
        es=sorted((e for e in events if w.test_start<=e.bar_index<w.test_end),key=lambda e:e.bar_index)
        sweeps=[e for e in es if e.event_type==EventType.LIQUIDITY_SWEEP]; mss=[e for e in es if e.event_type==EventType.MSS]; fvgs=[e for e in es if e.event_type==EventType.FVG]; rets=[e for e in es if e.event_type==EventType.RETEST]
        used_m=set(); used_f=set(); used_r=set(); seq=[]
        for s in sweeps:
            ms=next((x for x in mss if id(x) not in used_m and x.bar_index>s.bar_index and x.direction==s.direction and x.bar_index-s.bar_index<=50),None)
            if ms is None: continue
            used_m.add(id(ms))
            f=next((x for x in fvgs if id(x) not in used_f and x.bar_index>ms.bar_index and x.direction==ms.direction and x.bar_index-ms.bar_index<=20),None)
            if f is None: continue
            used_f.add(id(f))
            r=next((x for x in rets if id(x) not in used_r and x.bar_index>f.bar_index and x.direction==f.direction and x.bar_index-f.bar_index<=50),None)
            if r is None: continue
            used_r.add(id(r)); seq.append((s,ms,f,r))
        print('WINDOW',n)
        print('FULL_SEQUENCE',len(seq))
        for d in ('bullish','bearish'):
            q=[x for x in seq if x[0].direction.value==d]
            print(d.upper(),'FULL_SEQUENCE',len(q),'RETEST_BARS',[x[3].bar_index for x in q])

if __name__=='__main__': main()
