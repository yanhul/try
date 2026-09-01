#!/usr/bin/env python3
"""One-shot deterministic OOS evaluator. Protocol must already be frozen."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .hypothesis_research import evaluate_split
from .hypotheses import HYPOTHESES

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--candidate',required=True); ap.add_argument('--data',required=True); ap.add_argument('--protocol',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    root=Path(__file__).resolve().parents[1]; candidate_path=Path(a.candidate); out=root/a.out; protocol=json.loads((root/a.protocol).read_text())
    if protocol.get('status')!='FROZEN' or protocol.get('oos_selection_used') is not False: raise SystemExit('BLOCKED: OOS protocol is not frozen/clean')
    candidate=json.loads(candidate_path.read_text()); hid=candidate['hypothesis_id']
    if candidate.get('oos_selection_used') is not False: raise SystemExit('BLOCKED: candidate provenance violation')
    if hid not in HYPOTHESES: raise SystemExit(f'UNEXECUTABLE_HYPOTHESIS_ID:{hid}')
    data=(root/a.data).resolve(); bars=load_bars(data); splits=chronological_split(len(bars)); validate_splits(splits,len(bars))
    result=evaluate_split(bars,splits[2].start,splits[2].end,hid,0.01,2.0,0.0)
    m=result['metrics']; passed=(m.get('profit_factor') is not None and m['profit_factor']>=1.0 and m['total_return']>=0.0)
    payload={'schema_version':1,'bc':candidate['bc'],'parent_bc':candidate['parent_bc'],'hypothesis_id':hid,'candidate_hash':candidate['candidate_hash'],'dataset':{'path':str(data),'sha256':sha256(data),'bars':len(bars)},'split':{'name':'OOS','start':splits[2].start,'end':splits[2].end},'protocol_sha256':sha256(root/a.protocol),'execution':{'stop_fraction':0.01,'reward_multiple':2.0,'round_trip_cost':0.0},'oos_selection_used':False,'oos_executed':True,'metrics':m,'trade_count':m.get('trade_count'),'oos_passed':passed}
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2)+'\n'); print(json.dumps({'bc':candidate['bc'],'hypothesis_id':hid,'oos_passed':passed,'metrics':m},indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
