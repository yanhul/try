from collections import defaultdict
import csv
from engine.events import MarketBar
from engine.strategy import ReferenceStrategy
from engine.ledger import build_ledger
from engine.execution import execute_trades
from engine.risk_exit import FixedRiskRewardExit
from engine.walk_forward import generate_walk_forward

DATA='data/BTCUSDT_1h.csv'
TRAIN=1100; TEST=500; STEP=500

def load_bars():
    with open(DATA,newline='',encoding='utf-8-sig') as f:
        return [MarketBar(timestamp=r['timestamp'],open=float(r['open']),high=float(r['high']),low=float(r['low']),close=float(r['close']),volume=float(r['volume'])) for r in csv.DictReader(f)]

def metrics(trades):
    rets=[]; wins=losses=0
    for x in trades:
        e=x.ledger_trade.entry_price; p=x.exit.price; d=x.ledger_trade.direction.value
        r=(p/e-1) if d=='bullish' else (e/p-1)
        rets.append(r)
        if r>0: wins+=1
        elif r<0: losses+=1
    gross_w=sum(r for r in rets if r>0); gross_l=-sum(r for r in rets if r<0)
    equity=1.; peak=1.; dd=0.
    for r in rets:
        equity*=1+r; peak=max(peak,equity); dd=max(dd,(peak-equity)/peak)
    return {'trade_count':len(rets),'win_count':wins,'loss_count':losses,'win_rate':wins/len(rets) if rets else 0.,'total_return':equity-1.,'profit_factor':gross_w/gross_l if gross_l else float('inf'),'max_drawdown':dd}

def main():
    bars=load_bars(); events=ReferenceStrategy().process(bars); ledger=build_ledger(events); exit_policy=FixedRiskRewardExit(.01,2.)
    windows=generate_walk_forward(len(bars),TRAIN,TEST,STEP)
    for n,w in enumerate(windows):
        test_ledger=[t for t in ledger if w.test_start<=t.entry_bar<w.test_end]
        executed, skipped=execute_trades(bars,test_ledger,exit_policy,max_concurrent=1)
        groups=defaultdict(list)
        for x in executed: groups[x.ledger_trade.direction.value].append(x)
        print('WINDOW',n,'EXECUTED',len(executed),'SKIPPED_OVERLAP',skipped)
        for d in ('bullish','bearish'):
            print(d.upper(),metrics(groups[d]))

if __name__=='__main__': main()
