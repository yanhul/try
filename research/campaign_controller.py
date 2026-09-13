#!/usr/bin/env python3
"""Bounded research campaign wrapper with isolated campaign epochs."""
from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/'research'/'campaign_policy.json'; STATE=ROOT/'research'/'bc_lifecycle_state.json'
CANDIDATE_DIR=ROOT/'research'/'autonomous_candidates'; FAILURE_DIR=ROOT/'research'/'failure_analysis'
QUALIFY={'REJECT','PROMOTE_TO_FUTURE_OOS_TEST'}

def load(path,default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def save(state):
    state['updated_at']=datetime.now(timezone.utc).isoformat(); STATE.write_text(json.dumps(state,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def terminal(state,outcome,reason,screened,budget):
    state.update(campaign_terminal=True,campaign_outcome=outcome,campaign_terminal_reason=reason,campaign_screened=min(int(screened),int(budget))); save(state)
    print(f"CAMPAIGN_TERMINAL outcome={outcome} screened={state['campaign_screened']}/{budget}"); return 0

def qualifying_bcs(history,start=1):
    out=set()
    for x in history if isinstance(history,list) else []:
        if not isinstance(x,dict): continue
        raw=str(x.get('bc','')).strip()
        if raw.isdigit() and int(raw)>=int(start) and str(x.get('decision')) in QUALIFY: out.add(int(raw))
    return out

def _epoch_start(state,history):
    if state.get('campaign_epoch_initialized') and isinstance(state.get('campaign_start_bc'),int): return int(state['campaign_start_bc'])
    vals=[int(x['bc']) for x in history if isinstance(x,dict) and str(x.get('bc','')).isdigit() and x.get('next')=='AGENT_HYPOTHESIS']
    return min(vals) if vals else (min(qualifying_bcs(history)) if qualifying_bcs(history) else 1)

def _durable_completed_bcs(start=1):
    if not CANDIDATE_DIR.exists() or not FAILURE_DIR.exists(): return start-1
    c={int(p.stem[2:]) for p in CANDIDATE_DIR.glob('BC*.json') if p.stem[2:].isdigit()}
    f={int(p.stem[2:]) for p in FAILURE_DIR.glob('BC*.json') if p.stem[2:].isdigit()}
    n=start-1
    while n+1 in c and n+1 in f: n+=1
    return n

def reconcile_campaign_state(state,budget):
    history=state.get('history',[]) if isinstance(state.get('history',[]),list) else []
    start=_epoch_start(state,history); completed=_durable_completed_bcs(start)
    known={int(x['bc']) for x in history if isinstance(x,dict) and str(x.get('bc','')).isdigit() and int(x['bc'])>=start}
    repaired=0
    for bc in range(start,completed+1):
        if bc in known: continue
        c=load(CANDIDATE_DIR/f'BC{bc}.json',{}); f=load(FAILURE_DIR/f'BC{bc}.json',{}); d=f.get('decision')
        if d not in QUALIFY: continue
        history.append({'bc':bc,'decision':d,'hypothesis_id':c.get('hypothesis_id') or f.get('hypothesis_id'),'candidate_hash':c.get('candidate_hash') or f.get('candidate_hash'),'reason':f.get('reason')}); repaired+=1
    state['campaign_start_bc']=start; state['history']=sorted(history,key=lambda x:int(x.get('bc',0)) if isinstance(x,dict) and str(x.get('bc','')).isdigit() else 0)
    screened=len(qualifying_bcs(history,start)); state['campaign_screened']=min(screened,int(budget))
    if repaired: state['state_reconciled_from_durable_bc_artifacts']=True; print(f'CAMPAIGN_RECONCILED repaired_history={repaired} completed_bc={completed} start_bc={start} screened={screened}/{budget}')
    return completed,start,screened

def retry_resume_allowed(state):
    return not state.get('campaign_terminal') and not state.get('terminal') and state.get('phase')=='WAIT_RETRY' and int(state.get('retry_count',0))<int(os.environ.get('RESEARCH_MAX_RESUME_RETRIES','3')) and bool(state.get('last_error'))

def continuation_allowed(*,new_screened:int,phase:str|None,last_error:object,terminal_state:bool)->bool:
    return not terminal_state and phase not in {'WAIT_RETRY','HOLD'} and not last_error and new_screened>0

def _start_new_campaign_epoch(state,policy):
    pid=str(policy['campaign_id']); old=str(state.get('campaign_id') or '')
    if old==pid:
        if state.get('campaign_epoch_initialized') and isinstance(state.get('campaign_start_bc'),int) and int(state.get('next_bc') or 0)<int(state['campaign_start_bc']): state['next_bc']=int(state['campaign_start_bc']); save(state)
        return
    history=state.get('history',[]) if isinstance(state.get('history',[]),list) else []
    bcs=[int(x['bc']) for x in history if isinstance(x,dict) and str(x.get('bc','')).isdigit()]
    start=max(bcs+[int(state.get('current_bc') or state.get('last_bc') or 0)])+1
    state.update(campaign_id=pid,campaign_epoch_initialized=True,campaign_start_bc=start,next_bc=start,campaign_screened=0,campaign_terminal=False,campaign_outcome=None,campaign_terminal_reason=None,phase='OBSERVE',last_error=None,retry_count=0,terminal=False)
    print(f'CAMPAIGN_NEW_EPOCH id={pid} start_bc={start} prior_id={old or "none"}'); save(state)

def _epoch_seed_failure(parent,start):
    p=FAILURE_DIR/f'BC{parent}.json'
    if p.exists(): return None
    if parent==start-1:
        FAILURE_DIR.mkdir(parents=True,exist_ok=True); q=ROOT/'research'/'.epoch_seed_failure.json'
        q.write_text(json.dumps({'kind':'epoch_seed_failure','decision':'SEED_EPOCH','parent_bc':parent,'epoch_start_bc':start,'research_evidence':False,'repair_context':True,'reason':'Epoch seed only; no prior failure evidence. This artifact is bootstrap/repair context, not research evidence.'})+'\n',encoding='utf-8'); return q
    return None

def main():
    policy=load(POLICY,None)
    if not isinstance(policy,dict): print('CAMPAIGN_BLOCKED missing_policy'); return 2
    req={'campaign_id','max_screening_candidates','controller_batch_size','terminal_outcomes','promotion_requires'}
    if not req.issubset(policy): print('CAMPAIGN_BLOCKED incomplete_policy'); return 2
    budget=int(policy['max_screening_candidates']); batch=int(policy['controller_batch_size']); outcomes=set(policy['terminal_outcomes'])
    if budget<=0 or batch<=0 or batch>budget or not outcomes: print('CAMPAIGN_BLOCKED invalid_policy'); return 2
    state=load(STATE,{})
    _start_new_campaign_epoch(state,policy)
    _,start,screened=reconcile_campaign_state(state,budget)
    if state.get('campaign_terminal'):
        o=state.get('campaign_outcome')
        if o not in outcomes: print(f'CAMPAIGN_BLOCKED persisted_invalid_terminal_outcome={o}'); return 3
        print(f"CAMPAIGN_TERMINAL outcome={o} screened={state.get('campaign_screened',0)}/{budget}"); return 0
    if screened>=budget: return terminal(state,'NO_EDGE_FOUND','FIXED_SCREENING_BUDGET_EXHAUSTED',screened,budget)
    env=dict(os.environ); env['RESEARCH_MAX_ITERATIONS']=str(min(batch,budget-screened)); before=qualifying_bcs(state.get('history',[]),start)
    print(f'CAMPAIGN_START screened={screened}/{budget} batch={env["RESEARCH_MAX_ITERATIONS"]} start_bc={start}')
    expected=int(state.get('next_bc',start)); seed=_epoch_seed_failure(expected-1,start)
    if seed is not None: env['RESEARCH_EPOCH_SEED_FAILURE']=str(seed)
    try: rc=subprocess.run([sys.executable,'research/bc_controller.py'],cwd=ROOT,env=env).returncode
    finally:
        if seed is not None and seed.exists(): seed.unlink()
    if rc: return rc
    state=load(STATE,{}); _,start,after=reconcile_campaign_state(state,budget)
    if state.get('phase') in {'WAIT_RETRY','HOLD'} or state.get('last_error'):
        state['campaign_budget']=budget; state['campaign_id']=policy['campaign_id']; save(state); reason=state.get('last_error') or state.get('phase')
        if retry_resume_allowed(state): print(f'CAMPAIGN_CONTINUE_RETRY retry={state.get("retry_count",0)}/{os.environ.get("RESEARCH_MAX_RESUME_RETRIES","3")} reason={reason} screened={screened}/{budget}')
        else: print(f'CAMPAIGN_HOLD reason={reason} screened={screened}/{budget}')
        return 0
    history=state.get('history',[]); after_set=qualifying_bcs(history,start); new=after_set-before; state.update(campaign_screened=min(after,budget),campaign_budget=budget,campaign_id=policy['campaign_id'])
    if state.get('terminal'):
        raw=state.get('terminal_reason'); outcome='EDGE_FOUND' if raw=='OOS_PASS' else 'NO_EDGE_FOUND' if raw=='OOS_FAIL' else 'INCONCLUSIVE' if raw in {'HOLD','UNKNOWN'} else raw
        if outcome not in outcomes: print(f'CAMPAIGN_BLOCKED terminal_reason_not_in_policy={raw}'); save(state); return 3
        state.update(campaign_terminal=True,campaign_outcome=outcome,campaign_terminal_reason=raw); save(state); print(f'CAMPAIGN_TERMINAL outcome={outcome} screened={after}/{budget}'); return 0
    if after>=budget: return terminal(state,'NO_EDGE_FOUND','FIXED_SCREENING_BUDGET_EXHAUSTED',after,budget)
    if not continuation_allowed(new_screened=len(new),phase=state.get('phase'),last_error=state.get('last_error'),terminal_state=bool(state.get('terminal'))):
        save(state); print(f'CAMPAIGN_HOLD reason=NO_NEW_SCREENED_BC screened={after}/{budget}'); return 0
    save(state); print(f'CAMPAIGN_CONTINUE screened={after}/{budget}'); return 0

if __name__=='__main__': raise SystemExit(main())
