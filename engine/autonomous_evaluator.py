#!/usr/bin/env python3
"""Deterministic IS/Validation evaluator for registered or compiled candidates."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .hypothesis_research import evaluate_split
from .hypotheses import HYPOTHESES
EVALUATION_SPEC={"stop_fraction":0.01,"reward_multiple":2.0,"round_trip_cost":0.0}
def sha256(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()
def discovered_predicate(spec):
 def get(row,key): return float(row.get(key) or 0.0)
 def pred(ctx,direction):
  r=ctx['entry']; op=spec['operator']; a=get(r,spec['left']); b=get(r,spec.get('right','close'))
  if op=='identity': value=a
  elif op=='difference': value=a-b
  elif op=='ratio': value=a/b if b else 0.0
  else: raise ValueError('unsupported_discovery_operator')
  return value>float(spec['threshold']) if spec['direction']=='above' else value<float(spec['threshold'])
 return pred
def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('--candidate',required=True); ap.add_argument('--data',default='data/BTCUSDT_1h.csv'); ap.add_argument('--out',required=True); a=ap.parse_args()
 root=Path(__file__).resolve().parents[1]; candidate=json.loads(Path(a.candidate).read_text(encoding='utf-8')); hid=candidate['hypothesis_id']
 if hid=='discovered_primitive':
  if not candidate.get('discovery_spec'): raise SystemExit('UNEXECUTABLE_DISCOVERY_SPEC')
  predicate=discovered_predicate(candidate['discovery_spec'])
 elif hid in HYPOTHESES: predicate=HYPOTHESES[hid]
 else: raise SystemExit(f'UNEXECUTABLE_HYPOTHESIS_ID:{hid}')
 data=(root/a.data).resolve(); bars=load_bars(data); splits=chronological_split(len(bars)); validate_splits(splits,len(bars))
 is_result=evaluate_split(bars,splits[0].start,splits[0].end,predicate,EVALUATION_SPEC['stop_fraction'],EVALUATION_SPEC['reward_multiple'],EVALUATION_SPEC['round_trip_cost'])
 val_result=evaluate_split(bars,splits[1].start,splits[1].end,predicate,EVALUATION_SPEC['stop_fraction'],EVALUATION_SPEC['reward_multiple'],EVALUATION_SPEC['round_trip_cost'])
 vm=val_result['metrics']; passed=vm.get('profit_factor') is not None and vm['profit_factor']>=1.0 and vm['total_return']>=0.0
 result={'schema_version':2,'bc':candidate['bc'],'parent_bc':candidate['parent_bc'],'hypothesis_id':hid,'candidate_hash':candidate['candidate_hash'],'discovery_spec':candidate.get('discovery_spec'),'oos_selection_used':False,'oos_executed':False,'dataset':{'path':str(data),'sha256':sha256(data),'bars':len(bars)},'evaluation_spec':dict(EVALUATION_SPEC),'IS':is_result,'VALIDATION':val_result,'validation_passed':passed}
 out=root/a.out; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'bc':candidate['bc'],'hypothesis_id':hid,'validation_passed':passed,'IS':is_result['metrics'],'VALIDATION':val_result['metrics']},indent=2)); return 0
if __name__=='__main__':raise SystemExit(main())
