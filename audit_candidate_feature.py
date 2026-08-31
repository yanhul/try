from __future__ import annotations
import json
from pathlib import Path
from engine.backtest import load_bars
from engine.execution import execute_trades
from engine.ledger import build_ledger
from engine.metrics import Trade, calculate_metrics
from engine.risk_exit import FixedRiskRewardExit
from engine.strategy import ReferenceStrategy
from engine.data_split import chronological_split

ROOT=Path(__file__).resolve().parent
PENDING=ROOT/'research/bc_pending_candidate.json'
DATA='data/BTCUSDT_1h.csv'; STOP=0.01; TARGET=2.0; COST=0.0

def run(strategy,bars,start,end):
    events=strategy.process(bars[:end]); ledger=[t for t in build_ledger(events) if start<=t.entry_bar<end]
    executed,skipped=execute_trades(bars[:end],ledger,FixedRiskRewardExit(STOP,TARGET),max_concurrent=1)
    executed=[x for x in executed if x.exit.bar_index<end]
    trades=[Trade(entry=x.ledger_trade.entry_price,exit=x.exit.price,direction=x.ledger_trade.direction.value,entry_bar=x.ledger_trade.entry_bar,exit_bar=x.exit.bar_index,exit_reason=x.exit.reason) for x in executed]
    return {'events':sum(start<=e.bar_index<end for e in events),'ledger_trades':len(ledger),'executed_trades':len(trades),'skipped_overlap':skipped,'metrics':calculate_metrics(trades,COST)}

def feature_predicate(name):
    def pred(t,bars):
        entry=bars[t.entry_bar]; sweep=bars[t.sweep_bar]; direction=t.direction.value
        if name=='entry_close_location':
            rng=entry.high-entry.low; x=.5 if rng<=0 else ((entry.close-entry.low)/rng if direction=='bullish' else (entry.high-entry.close)/rng); return x>=.5
        if name=='entry_signed_body':
            rng=entry.high-entry.low; x=0 if rng<=0 else (entry.close-entry.open)/rng; return (x>=0 if direction=='bullish' else -x>=0)
        if name=='sweep_close_location':
            rng=sweep.high-sweep.low; x=.5 if rng<=0 else ((sweep.close-sweep.low)/rng if direction=='bullish' else (sweep.high-sweep.close)/rng); return x>=.5
        if name=='sweep_signed_body':
            body=sweep.close-sweep.open; return body>=0 if direction=='bullish' else body<=0
        if name.startswith('fast_entry_le_'):
            return t.entry_bar-t.sweep_bar <= int(name.rsplit('_',1)[1].replace('bar',''))
        raise ValueError(name)
    return pred

def main():
    if not PENDING.exists(): print('LIFECYCLE_STOP NO_PENDING_REGISTERED_CANDIDATE'); return 0
    c=json.loads(PENDING.read_text()); name=c['feature']; bars=load_bars(DATA); is_split,val_split,oos_split=chronological_split(len(bars)); pred=feature_predicate(name)
    gates=[]
    for split in (is_split,val_split):
        base=run(ReferenceStrategy(False,False),bars,split.start,split.end)
        events=ReferenceStrategy(False,False).process(bars[:split.end]); ledger=[t for t in build_ledger(events) if split.start<=t.entry_bar<split.end]
        chosen=[t for t in ledger if pred(t,bars)]
        executed,skipped=execute_trades(bars[:split.end],chosen,FixedRiskRewardExit(STOP,TARGET),max_concurrent=1)
        executed=[x for x in executed if x.exit.bar_index<split.end]
        trades=[Trade(entry=x.ledger_trade.entry_price,exit=x.exit.price,direction=x.ledger_trade.direction.value,entry_bar=x.ledger_trade.entry_bar,exit_bar=x.exit.bar_index,exit_reason=x.exit.reason) for x in executed]
        cand={'events':len(chosen),'ledger_trades':len(chosen),'executed_trades':len(trades),'skipped_overlap':skipped,'metrics':calculate_metrics(trades,COST)}; bm,cm=base['metrics'],cand['metrics']; dd=bm['max_drawdown']*1.25 if bm['max_drawdown']>0 else 0.0
        gate=cm['total_return']>bm['total_return'] and cm['max_drawdown']<=dd and cand['executed_trades']>=5
        print('SPLIT',split.name); print('BC1',base); print('CANDIDATE',cand); print('DELTA',{'return_delta':cm['total_return']-bm['total_return'],'pf_delta':(cm['profit_factor'] or 0)-(bm['profit_factor'] or 0),'dd_delta':cm['max_drawdown']-bm['max_drawdown'],'trade_delta':cand['executed_trades']-base['executed_trades']}); print('SPLIT_GATE',gate); gates.append(gate)
    d=f'PROMOTE_TO_FUTURE_OOS_TEST_{name}' if all(gates) else f'REJECT_CANDIDATE_{name}'; print('DECISION',d); print('OOS_SPLIT_RESERVED',{'start':oos_split.start,'end':oos_split.end}); return 0
if __name__=='__main__': raise SystemExit(main())
