#!/usr/bin/env python3
"""One-shot deterministic OOS evaluator. Protocol must already be frozen."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .hypothesis_research import evaluate_split
from .hypotheses import HYPOTHESES
from .autonomous_evaluator import discovered_predicate, mechanism_predicate, EVALUATION_SPEC
from research.cost_model import DEFAULT_COST_MODEL


def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--candidate',required=True); ap.add_argument('--data',required=True); ap.add_argument('--protocol',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    root=Path(__file__).resolve().parents[1]; candidate_path=Path(a.candidate); out=root/a.out; protocol=json.loads((root/a.protocol).read_text())
    if protocol.get('status')!='FROZEN' or protocol.get('oos_selection_used') is not False: raise SystemExit('BLOCKED: OOS protocol is not frozen/clean')
    candidate=json.loads(candidate_path.read_text()); hid=candidate['hypothesis_id']; spec=candidate.get('discovery_spec') or {}
    if candidate.get('oos_selection_used') is not False: raise SystemExit('BLOCKED: candidate provenance violation')
    if hid=='discovered_primitive':
        if not isinstance(spec,dict): raise SystemExit('UNEXECUTABLE_DISCOVERY_SPEC')
        predicate=discovered_predicate(spec); candidate_universe='all_bars'; candidate_family='discovered_primitive'; predicate_name='discovered_primitive'
    elif hid=='mechanism_family':
        if not isinstance(spec,dict): raise SystemExit('UNEXECUTABLE_MECHANISM_SPEC')
        predicate=mechanism_predicate(spec); family=spec.get('mechanism_family'); candidate_universe='reference_event_ledger' if family in {'smc_ict','fvg_imbalance'} else 'all_bars'; candidate_family=family; predicate_name='mechanism_family'
    elif hid in HYPOTHESES:
        predicate=HYPOTHESES[hid]; candidate_universe='reference_event_ledger'; candidate_family=None; predicate_name=hid
    else: raise SystemExit(f'UNEXECUTABLE_HYPOTHESIS_ID:{hid}')
    data=(root/a.data).resolve(); bars=load_bars(data); splits=chronological_split(len(bars)); validate_splits(splits,len(bars))
    kwargs={'candidate_universe':candidate_universe,'candidate_family':candidate_family,'candidate_spec':spec}
    cost_model=DEFAULT_COST_MODEL
    result=evaluate_split(bars,splits[2].start,splits[2].end,predicate,EVALUATION_SPEC['stop_fraction'],EVALUATION_SPEC['reward_multiple'],cost_model=cost_model,**kwargs)
    m=result['metrics']; passed=(m.get('profit_factor') is not None and m['profit_factor']>=1.0 and m['total_return']>=0.0)
    dataset_sha=sha256(data); protocol_sha=sha256(root/a.protocol); candidate_sha=candidate['candidate_hash']
    payload={'schema_version':2,'bc':candidate['bc'],'parent_bc':candidate['parent_bc'],'hypothesis_id':hid,'candidate_hash':candidate_sha,'discovery_spec':candidate.get('discovery_spec'),'candidate_universe':candidate_universe,'candidate_family':candidate_family,'dataset':{'path':str(data),'sha256':dataset_sha,'bars':len(bars)},'split':{'name':'OOS','start':splits[2].start,'end':splits[2].end},'protocol_sha256':protocol_sha,'evaluation_spec':dict(EVALUATION_SPEC),'cost_model':cost_model.metadata(),'execution':{'stop_fraction':EVALUATION_SPEC['stop_fraction'],'reward_multiple':EVALUATION_SPEC['reward_multiple']},'oos_selection_used':False,'oos_executed':True,'predicate':predicate_name,'metrics':m,'trade_count':m.get('trade_count'),'oos_passed':passed}
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2)+'\n')
    result_sha=sha256(out)
    receipt=out.with_name(out.stem+'_receipt.json')
    receipt_payload={'schema_version':1,'receipt_type':'OOS_EXECUTION_RECEIPT','bc':candidate['bc'],'candidate_hash':candidate_sha,'result_sha256':result_sha,'dataset_sha256':dataset_sha,'protocol_sha256':protocol_sha,'split':payload['split'],'oos_selection_used':False,'oos_executed':True,'oos_passed':passed,'metrics':m,'predicate':predicate_name}
    receipt_payload['receipt_id']=hashlib.sha256(json.dumps(receipt_payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    receipt.write_text(json.dumps(receipt_payload,indent=2)+'\n')
    print(json.dumps({'bc':candidate['bc'],'hypothesis_id':hid,'candidate_universe':candidate_universe,'oos_passed':passed,'metrics':m,'receipt':str(receipt)},indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
