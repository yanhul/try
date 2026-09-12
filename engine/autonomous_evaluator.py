#!/usr/bin/env python3
"""Deterministic IS/Validation evaluator for registered or compiled candidates."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .hypothesis_research import evaluate_split
from .hypotheses import HYPOTHESES

# The current reference execution has no authoritative fee/slippage model.
# Therefore validation_passed is explicitly a GROSS validation result only;
# net_validation_gate remains blocked until a real cost model is supplied.
EVALUATION_SPEC={"stop_fraction":0.01,"reward_multiple":2.0,"round_trip_cost":0.0,"cost_model_status":"UNAVAILABLE","validation_basis":"GROSS_ONLY"}
WINDOWS={3,5,10,20,50,100}

def sha256(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()

def series_value(ctx,key): return float(ctx['entry'].get(key) or 0.0)

def discovered_predicate(spec):
 op=spec['operator']; left=spec['left']; right=spec.get('right'); w=spec.get('window')
 def pred(ctx,direction):
  a=series_value(ctx,left); b=series_value(ctx,right) if right else 0.0
  history=ctx.get('history',[]) or []
  vals=[float(x.get(left) or 0.0) for x in history]
  if op=='identity': value=a
  elif op=='difference': value=a-b
  elif op=='ratio': value=a/b if b else 0.0
  elif op in {'rolling_mean','rolling_std','zscore','lag','delta','rank'}:
   if not isinstance(w,int) or w not in WINDOWS or len(vals)<w: return False
   window=vals[-w:]
   if op=='rolling_mean': value=sum(window)/w
   elif op=='rolling_std':
    mean=sum(window)/w; value=math.sqrt(sum((x-mean)**2 for x in window)/w)
   elif op=='zscore':
    mean=sum(window)/w; sd=math.sqrt(sum((x-mean)**2 for x in window)/w); value=(a-mean)/sd if sd else 0.0
   elif op=='lag': value=vals[-w]
   elif op=='delta': value=a-vals[-w]
   else: value=sum(x<=a for x in window)/w
  else: raise ValueError('unsupported_discovery_operator')
  threshold=float(spec.get('threshold',0.0))
  return value>threshold if spec.get('direction')=='above' else value<threshold
 return pred

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('--candidate',required=True); ap.add_argument('--data',default='data/BTCUSDT_1h.csv'); ap.add_argument('--out',required=True); a=ap.parse_args()
 root=Path(__file__).resolve().parents[1]; candidate=json.loads(Path(a.candidate).read_text(encoding='utf-8')); hid=candidate['hypothesis_id']
 if hid=='discovered_primitive':
  if not isinstance(candidate.get('discovery_spec'),dict): raise SystemExit('UNEXECUTABLE_DISCOVERY_SPEC')
  predicate=discovered_predicate(candidate['discovery_spec'])
 elif hid in HYPOTHESES: predicate=HYPOTHESES[hid]
 else: raise SystemExit(f'UNEXECUTABLE_HYPOTHESIS_ID:{hid}')
 data=(root/a.data).resolve(); bars=load_bars(data); splits=chronological_split(len(bars)); validate_splits(splits,len(bars))
 is_result=evaluate_split(bars,splits[0].start,splits[0].end,predicate,EVALUATION_SPEC['stop_fraction'],EVALUATION_SPEC['reward_multiple'],EVALUATION_SPEC['round_trip_cost'])
 val_result=evaluate_split(bars,splits[1].start,splits[1].end,predicate,EVALUATION_SPEC['stop_fraction'],EVALUATION_SPEC['reward_multiple'],EVALUATION_SPEC['round_trip_cost'])
 vm=val_result['metrics']; gross_passed=vm.get('profit_factor') is not None and vm['profit_factor']>=1.0 and vm['total_return']>=0.0
 net_gate='PASS' if EVALUATION_SPEC['cost_model_status']=='AVAILABLE' and gross_passed else ('COST_MODEL_REQUIRED' if EVALUATION_SPEC['cost_model_status']!='AVAILABLE' else 'GROSS_VALIDATION_FAILED')
 result={'schema_version':5,'bc':candidate['bc'],'parent_bc':candidate['parent_bc'],'hypothesis_id':hid,'candidate_hash':candidate['candidate_hash'],'discovery_spec':candidate.get('discovery_spec'),'oos_selection_used':False,'oos_executed':False,'dataset':{'path':str(data),'sha256':sha256(data),'bars':len(bars)},'evaluation_spec':dict(EVALUATION_SPEC),'IS':is_result,'VALIDATION':val_result,'gross_validation_passed':gross_passed,'net_validation_gate':net_gate,'validation_passed':gross_passed,'validation_basis':'GROSS_ONLY'}
 out=root/a.out; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'bc':candidate['bc'],'hypothesis_id':hid,'gross_validation_passed':gross_passed,'net_validation_gate':net_gate,'validation_passed':gross_passed,'validation_basis':'GROSS_ONLY'},indent=2)); return 0
if __name__=='__main__':raise SystemExit(main())
