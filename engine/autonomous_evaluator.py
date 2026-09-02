#!/usr/bin/env python3
"""Deterministic IS/Validation evaluator for one registered autonomous candidate.

OOS is deliberately never touched here. Promotion is decided only from IS/Validation.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .hypothesis_research import evaluate_split
from .hypotheses import HYPOTHESES

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--candidate',required=True)
    ap.add_argument('--data',default='research/BTCUSDT_1h_events.csv')
    ap.add_argument('--out',required=True)
    ap.add_argument('--stop',type=float,default=0.01)
    ap.add_argument('--rr',type=float,default=2.0)
    ap.add_argument('--cost',type=float,default=0.0)
    a=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    candidate=json.loads(Path(a.candidate).read_text(encoding='utf-8'))
    hid=candidate['hypothesis_id']
    if hid not in HYPOTHESES: raise SystemExit(f'UNEXECUTABLE_HYPOTHESIS_ID:{hid}')
    data=(root/a.data).resolve()
    bars=load_bars(data)
    splits=chronological_split(len(bars)); validate_splits(splits,len(bars))
    predicate=HYPOTHESES[hid]
    is_result=evaluate_split(bars,splits[0].start,splits[0].end,predicate,a.stop,a.rr,a.cost)
    val_result=evaluate_split(bars,splits[1].start,splits[1].end,predicate,a.stop,a.rr,a.cost)
    vm=val_result['metrics']
    passed=(vm.get('profit_factor') is not None and vm['profit_factor']>=1.0 and vm['total_return']>=0.0)
    result={
      'schema_version':1,'bc':candidate['bc'],'parent_bc':candidate['parent_bc'],
      'hypothesis_id':hid,'candidate_hash':candidate['candidate_hash'],
      'oos_selection_used':False,'oos_executed':False,
      'dataset':{'path':str(data),'sha256':sha256(data),'bars':len(bars)},
      'execution':{'stop_fraction':a.stop,'reward_multiple':a.rr,'round_trip_cost':a.cost},
      'IS':is_result,'VALIDATION':val_result,'validation_passed':passed
    }
    out=root/a.out; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'bc':candidate['bc'],'hypothesis_id':hid,'validation_passed':passed,'IS':is_result['metrics'],'VALIDATION':val_result['metrics']},indent=2))
    return 0
if __name__=='__main__': raise SystemExit(main())
