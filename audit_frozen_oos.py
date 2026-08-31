#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from engine.backtest import load_bars
from engine.data_split import chronological_split
from engine.execution import execute_trades
from engine.ledger import build_ledger
from engine.metrics import Trade, calculate_metrics
from engine.risk_exit import FixedRiskRewardExit
from engine.strategy import ReferenceStrategy
ROOT=Path(__file__).resolve().parent
PENDING=ROOT/'research/bc_pending_candidate.json'; RESULT=ROOT/'research/oos_result.json'
DATA='data/BTCUSDT_1h.csv'; STOP=0.01; TARGET=2.0; COST=0.0
def run(ledger,bars,start,end):
    executed,skipped=execute_trades(bars[:end],ledger,FixedRiskRewardExit(STOP,TARGET),max_concurrent=1); executed=[x for x in executed if x.exit.bar_index<end]
    trades=[Trade(entry=x.ledger_trade.entry_price,exit=x.exit.price,direction=x.ledger_trade.direction.value,entry_bar=x.ledger_trade.entry_bar,exit_bar=x.exit.bar_index,exit_reason=x.exit.reason) for x in executed]
    return {'ledger_trades':len(ledger),'executed_trades':len(trades),'skipped_overlap':skipped,'metrics':calculate_metrics(trades,COST)}
def predicate(name,t,bars):
    entry=bars[t.entry_bar]; sweep=bars[t.sweep_bar]; direction=t.direction.value
    if name=='entry_close_location':
        rng=entry.high-entry.low; x=.5 if rng<=0 else ((entry.close-entry.low)/rng if direction=='bullish' else (entry.high-entry.close)/rng); return x>=.5
    if name=='entry_signed_body':
        rng=entry.high-entry.low; x=0 if rng<=0 else (entry.close-entry.open)/rng; return x>=0 if direction=='bullish' else -x>=0
    if name=='sweep_close_location':
        rng=sweep.high-sweep.low; x=.5 if rng<=0 else ((sweep.close-sweep.low)/rng if direction=='bullish' else (sweep.high-sweep.close)/rng); return x>=.5
    if name=='sweep_signed_body':
        body=sweep.close-sweep.open; return body>=0 if direction=='bullish' else body<=0
    if name.startswith('fast_entry_le_'): return t.entry_bar-t.sweep_bar<=int(name.rsplit('_',1)[1].replace('bar',''))
    raise ValueError(name)
def main():
    if not PENDING.exists(): print('OOS_STOP NO_FROZEN_CANDIDATE'); return 0
    candidate=json.loads(PENDING.read_text(encoding='utf-8')); name=candidate['feature']; bars=load_bars(DATA); is_split,val_split,oos_split=chronological_split(len(bars))
    base_events=ReferenceStrategy(False,False).process(bars[:oos_split.end]); base_ledger=[t for t in build_ledger(base_events) if oos_split.start<=t.entry_bar<oos_split.end]; cand_ledger=[t for t in base_ledger if predicate(name,t,bars)]
    baseline=run(base_ledger,bars,oos_split.start,oos_split.end); candidate_result=run(cand_ledger,bars,oos_split.start,oos_split.end); bm,cm=baseline['metrics'],candidate_result['metrics']
    result={'schema_version':1,'candidate':candidate.get('candidate'),'feature':name,'frozen_parameter_hash':candidate.get('frozen_parameter_hash'),'data':'data/BTCUSDT_1h.csv','oos_start_bar':oos_split.start,'oos_end_bar':oos_split.end,'cost':COST,'stop':STOP,'target_r':TARGET,'selection':False,'oos_touched_before_test':False,'baseline':baseline,'candidate_result':candidate_result,'delta':{'return_delta':cm['total_return']-bm['total_return'],'pf_delta':(cm['profit_factor'] or 0.0)-(bm['profit_factor'] or 0.0),'dd_delta':cm['max_drawdown']-bm['max_drawdown'],'trade_delta':candidate_result['executed_trades']-baseline['executed_trades']},'oos_verdict':'HOLD_NO_PREREGISTERED_OOS_CRITERIA'}
    RESULT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('FROZEN_OOS_STATUS',{'candidate':name,'selection':False,'oos_touched_before_test':False,'oos_start':oos_split.start,'oos_end':oos_split.end,'frozen_parameter_hash':candidate.get('frozen_parameter_hash')})
    print('OOS_BASELINE',baseline); print('OOS_CANDIDATE',candidate_result); print('OOS_DELTA',result['delta']); print('OOS_VERDICT HOLD_NO_PREREGISTERED_OOS_CRITERIA'); return 0
if __name__=='__main__': raise SystemExit(main())
