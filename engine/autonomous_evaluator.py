#!/usr/bin/env python3
"""Deterministic IS/Validation evaluator for registered, compiled, or mechanism-family candidates."""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
from .backtest import load_bars
from .data_split import chronological_split,validate_splits
from .hypothesis_research import evaluate_split
from .hypotheses import HYPOTHESES
from research.cost_model import DEFAULT_COST_MODEL

EVALUATION_SPEC={"stop_fraction":0.01,"reward_multiple":2.0,"round_trip_cost":0.0,"cost_model_status":"AVAILABLE","validation_basis":"NET_REQUIRED_FOR_PROMOTION"}
WINDOWS={3,5,10,20,50,100}
MECHANISMS={"momentum_trend","mean_reversion","volatility","smc_ict","fvg_imbalance","wyckoff_vsa_vpa","vwap_volume_profile","regime","seasonality","point_figure","gann_reference"}
EVENT_MECHANISMS={"smc_ict","fvg_imbalance"}


def sha256(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()

def series_value(ctx,key):
 value=ctx.get('entry',{}).get(key)
 if value is None:return None
 try:value=float(value)
 except (TypeError,ValueError):return None
 return value if math.isfinite(value) else None

def discovered_value(spec,ctx):
 op=spec['operator'];left=spec['left'];right=spec.get('right');w=spec.get('window')
 a=series_value(ctx,left);b=series_value(ctx,right) if right else None
 if a is None or (right and b is None):return None
 history=ctx.get('history',[]) or [];vals=[]
 for x in history:
  v=x.get(left)
  try:v=float(v)
  except (TypeError,ValueError):return None
  if not math.isfinite(v):return None
  vals.append(v)
 if op=='identity':value=a
 elif op=='difference':value=a-b
 elif op=='ratio':
  if b==0:return None
  value=a/b
 elif op in {'rolling_mean','rolling_std','zscore','lag','delta','rank'}:
  if not isinstance(w,int) or w not in WINDOWS or len(vals)<w:return None
  window=vals[-w:]
  if op=='rolling_mean':value=sum(window)/w
  elif op=='rolling_std':
   mean=sum(window)/w;value=math.sqrt(sum((x-mean)**2 for x in window)/w)
  elif op=='zscore':
   mean=sum(window)/w;sd=math.sqrt(sum((x-mean)**2 for x in window)/w);value=(a-mean)/sd if sd else 0.0
  elif op=='lag':value=vals[-w]
  elif op=='delta':value=a-vals[-w]
  else:value=sum(x<=a for x in window)/w
 else:return None
 return value if math.isfinite(value) else None

def discovered_predicate(spec):
 direction=spec['direction'];threshold=float(spec['threshold'])
 def pred(ctx,trade_direction):
  value=discovered_value(spec,ctx)
  if value is None:return False
  signal_direction='bullish' if direction=='above' else 'bearish'
  return trade_direction==signal_direction and (value>threshold if direction=='above' else value<threshold)
 return pred

def mechanism_value(ctx,family):
 row=ctx.get('entry',{})
 if family=='momentum_trend':return row.get('momentum_trend')
 if family=='mean_reversion':return row.get('mean_reversion')
 if family=='volatility':return row.get('volatility')
 if family=='wyckoff_vsa_vpa':return row.get('wyckoff_vsa_vpa')
 if family=='vwap_volume_profile':return row.get('vwap_volume_profile')
 if family=='regime':return 1.0 if row.get('mtf_fast_bullish') else -1.0
 if family=='seasonality':return float(row.get('seasonality',0))
 if family=='point_figure':return 1.0 if row.get('point_figure')=='X' else -1.0
 if family=='gann_reference':return row.get('gann_reference')
 return None

def mechanism_predicate(spec):
 family=spec['mechanism_family'];threshold=float(spec.get('threshold',0));comparison=spec.get('direction','above')
 if family not in MECHANISMS:raise ValueError('invalid_mechanism_family')
 def pred(ctx,trade_direction):
  if family in EVENT_MECHANISMS:
   event_key='smc_ict' if family=='smc_ict' else 'fvg_imbalance'
   return trade_direction==ctx.get('entry',{}).get('event_direction',trade_direction) and bool(ctx.get(event_key) or ctx.get('entry',{}).get(event_key))
  value=mechanism_value(ctx,family)
  if value is None:return False
  if family=='mean_reversion':
   if trade_direction=='bullish':return value < -abs(threshold) if threshold else value < 0
   return value > abs(threshold) if threshold else value > 0
  if family in {'volatility','seasonality'}:
   return (value>threshold if comparison=='above' else value<threshold)
  expected='bullish' if comparison=='above' else 'bearish'
  if trade_direction!=expected:return False
  return value>threshold if comparison=='above' else value<threshold
 return pred

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',required=True);ap.add_argument('--data',default='data/BTCUSDT_1h.csv');ap.add_argument('--out',required=True);a=ap.parse_args()
 root=Path(__file__).resolve().parents[1];candidate=json.loads(Path(a.candidate).read_text(encoding='utf-8'));hid=candidate['hypothesis_id'];spec=candidate.get('discovery_spec') or {}
 if hid=='discovered_primitive':
  if not isinstance(spec,dict):raise SystemExit('UNEXECUTABLE_DISCOVERY_SPEC')
  predicate=discovered_predicate(spec);candidate_universe='all_bars';candidate_family='discovered_primitive'
 elif hid=='mechanism_family':
  if not isinstance(spec,dict):raise SystemExit('UNEXECUTABLE_MECHANISM_SPEC')
  predicate=mechanism_predicate(spec);family=spec.get('mechanism_family');candidate_universe='reference_event_ledger' if family in EVENT_MECHANISMS else 'all_bars';candidate_family=family
 elif hid in HYPOTHESES:
  predicate=HYPOTHESES[hid];candidate_universe='reference_event_ledger';candidate_family=None
 else:raise SystemExit(f'UNEXECUTABLE_HYPOTHESIS_ID:{hid}')
 data=(root/a.data).resolve();bars=load_bars(data);splits=chronological_split(len(bars));validate_splits(splits,len(bars))
 kwargs={"candidate_universe":candidate_universe,"candidate_family":candidate_family,"candidate_spec":spec}
 is_result=evaluate_split(bars,splits[0].start,splits[0].end,predicate,EVALUATION_SPEC['stop_fraction'],EVALUATION_SPEC['reward_multiple'],EVALUATION_SPEC['round_trip_cost'],cost_model=DEFAULT_COST_MODEL,**kwargs)
 val_result=evaluate_split(bars,splits[1].start,splits[1].end,predicate,EVALUATION_SPEC['stop_fraction'],EVALUATION_SPEC['reward_multiple'],EVALUATION_SPEC['round_trip_cost'],cost_model=DEFAULT_COST_MODEL,**kwargs)
 vm=val_result['metrics'];gross_passed=vm.get('profit_factor') is not None and vm['profit_factor']>=1.0 and vm['total_return']>=0.0;cost_available=EVALUATION_SPEC.get('cost_model_status')=='AVAILABLE';net_gate='PASS' if cost_available and gross_passed else ('COST_MODEL_REQUIRED' if not cost_available else 'GROSS_VALIDATION_FAILED');validation_passed=bool(cost_available and gross_passed)
 result={'schema_version':8,'bc':candidate['bc'],'parent_bc':candidate['parent_bc'],'hypothesis_id':hid,'candidate_hash':candidate['candidate_hash'],'discovery_spec':candidate.get('discovery_spec'),'oos_selection_used':False,'oos_executed':False,'dataset':{'path':str(data),'sha256':sha256(data),'bars':len(bars)},'evaluation_spec':dict(EVALUATION_SPEC),'candidate_universe':candidate_universe,'cost_model':DEFAULT_COST_MODEL.metadata(),'IS':is_result,'VALIDATION':val_result,'gross_validation_passed':gross_passed,'net_validation_gate':net_gate,'validation_passed':validation_passed,'validation_basis':'NET_REQUIRED_FOR_PROMOTION'}
 out=root/a.out;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'bc':candidate['bc'],'hypothesis_id':hid,'candidate_universe':candidate_universe,'gross_validation_passed':gross_passed,'net_gate':net_gate},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
