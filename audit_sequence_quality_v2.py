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
        es=sorted((e for e in events if w.test_start<=e.bar_index<w.test_end),key=lambda e:(e.bar_index,e.event_type.value))
        sweeps=[e for e in es if e.event_type==EventType.LIQUIDITY_SWEEP]
        mss=[e for e in es if e.event_type==EventType.MSS]
        fvgs=[e for e in es if e.event_type==EventType.FVG]
        rets=[e for e in es if e.event_type==EventType.RETEST]
        # Greedy one-to-one forward matching: each stage must occur strictly after its predecessor.
        def match(prev, candidates, max_gap=None):
            out=[]; j=0
            for p in prev:
                while j<len(candidates) and candidates[j].bar_index<=p.bar_index: j+=1
                if j>=len(candidates): break
                if max_gap is not None and candidates[j].bar_index-p.bar_index>max_gap: continue
                out.append(candidates[j]); j+=1
            return out
        m=match(sweeps,mss,50)
        f=match(m,fvgs,20)
        r=match(f,rets,50)
        print('WINDOW',n)
        print('SWEEP',len(sweeps),'MSS',len(mss),'FVG',len(fvgs),'RETEST',len(rets))
        print('SWEEP_TO_MSS',len(m)/len(sweeps) if sweeps else 0)
        print('MSS_TO_FVG',len(f)/len(m) if m else 0)
        print('FVG_TO_RETEST',len(r)/len(f) if f else 0)
        print('FULL_SEQUENCE',len(r))
        print('RETEST_DIRECTIONS',Counter(e.direction.value for e in r))

if __name__=='__main__': main()
