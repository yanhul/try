from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'research'/'bc_lifecycle_state.json'; QUEUE=ROOT/'research'/'bc_queue.json'
FAILURE_DIR=ROOT/'research'/'failure_analysis'; CANDIDATE_DIR=ROOT/'research'/'autonomous_candidates'; FREEZE_DIR=ROOT/'research'/'frozen_candidates'; OOS_DIR=ROOT/'research'/'oos'
PROMOTE='PROMOTE_TO_FUTURE_OOS_TEST'; REJECT='REJECT_BC'; MAX=int(os.environ.get('RESEARCH_MAX_ITERATIONS','8'))
from contracts import validate_candidate, validate_evaluation, transition

def run(cmd,env=None):
 p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,env=env); out=p.stdout+p.stderr; print(out,end=''); return p.returncode,out
def load(p,d): return json.loads(p.read_text(encoding='utf-8')) if p.exists() else d
def save(s): s['updated_at']=datetime.now(timezone.utc).isoformat(); STATE.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def gate(bc):
 p=ROOT/'audit_bc_fast_gate.py'
 if p.exists(): return p
 p=ROOT/f'audit_bc{bc}_fast_gate.py'; return p if p.exists() else None
def write_queue(q): QUEUE.write_text(json.dumps(q,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def used_ids(s): return sorted({str(x['hypothesis_id']) for x in s.get('history',[]) if x.get('hypothesis_id')})
def regenerate(bc,parent,failure,s):
 output=CANDIDATE_DIR/f'BC{bc}.json'; output.parent.mkdir(parents=True,exist_ok=True)
 if output.exists(): output.unlink()
 env=os.environ.copy(); env.update(RESEARCH_PARENT_BC=str(parent),RESEARCH_FAILURE_ANALYSIS=str(failure),RESEARCH_NEXT_BC=str(bc),RESEARCH_CANDIDATE_OUTPUT=str(output),RESEARCH_USED_HYPOTHESIS_IDS=','.join(used_ids(s)))
 rc,out=run([sys.executable,'research/provider_router.py'],env=env)
 if 'PROVIDER_ROUTER_HOLD' in out or ('PROVIDER_FAIL' in out and 'PROVIDER_SELECTED' not in out): return False
 return rc==0 and output.exists()
def normalize_queue(s):
 q=load(QUEUE,[]); expected=int(s.get('next_bc',int(s.get('last_bc') or 0)+1)); active=[x for x in q if isinstance(x,dict) and int(x.get('bc',-1))==expected and int(x.get('parent_bc',expected-1))==expected-1]
 if len(active)>1: active=active[:1]
 if q != active: write_queue(active)
 return active
def oos_once(bc,candidate):
 protocol=ROOT/'research'/'oos_protocol.json'; out=OOS_DIR/f'BC{bc}_oos_result.json'; freeze=FREEZE_DIR/f'BC{bc}.json'
 if not protocol.exists(): print('OOS_HOLD_PROTOCOL_MISSING'); return None
 FREEZE_DIR.mkdir(parents=True,exist_ok=True); OOS_DIR.mkdir(parents=True,exist_ok=True)
 candidate_hash=candidate['candidate_hash']
 if freeze.exists():
  frozen=load(freeze,{})
  if frozen.get('candidate_hash')!=candidate_hash: print('OOS_HOLD_FROZEN_HASH_MISMATCH'); return None
 else: freeze.write_text(json.dumps(candidate,indent=2)+'\n',encoding='utf-8')
 if out.exists():
  result=load(out,{})
  if result.get('candidate_hash')!=candidate_hash or result.get('oos_executed') is not True: print('OOS_HOLD_EXISTING_ARTIFACT_INVALID'); return None
  return result
 rc,_=run([sys.executable,'-m','engine.oos_runner','--candidate',str(freeze),'--data','data/BTCUSDT_1h.csv','--protocol','research/oos_protocol.json','--out',str(out)])
 if rc or not out.exists(): print(f'CONTROLLER_DECISION HOLD_OOS_EXECUTOR BC{bc}'); return None
 return load(out,{})
def main():
 s=load(STATE,{'history':[],'iterations':0,'last_bc':None,'next_bc':1,'oos_consumed':[],'terminal':False})
 if s.get('terminal'): print('CONTROLLER_DECISION TERMINAL_STATE'); return 0
 q=normalize_queue(s)
 if not q:
  expected=int(s.get('next_bc',int(s.get('last_bc') or 0)+1)); parent=expected-1
  if parent==0: print('CONTROLLER_DECISION HOLD_NO_REGISTERED_BASELINE'); return 0
  failure=FAILURE_DIR/f'BC{parent}.json'
  if not failure.exists(): print(f'CONTROLLER_DECISION HOLD_NO_FAILURE_ANALYSIS BC{parent}'); return 0
  if not regenerate(expected,parent,failure,s): print(f'CONTROLLER_DECISION HOLD_PROVIDER_ROUTER BC{expected}'); return 0
  candidate=json.loads((CANDIDATE_DIR/f'BC{expected}.json').read_text(encoding='utf-8')); validate_candidate(candidate); write_queue([candidate]); q=[candidate]
 for _ in range(MAX):
  q=normalize_queue(s)
  if not q: print('CONTROLLER_DECISION HOLD_EMPTY_QUEUE'); return 0
  c=q[0]; bc=int(c['bc']); parent=int(c.get('parent_bc',bc-1)); candidate=CANDIDATE_DIR/f'BC{bc}.json'; g=gate(bc)
  if not g: print(f'CONTROLLER_DECISION HOLD_NO_GATE BC{bc}'); return 0
  try:
   from autonomous_hypothesis import load_candidate
   cand=load_candidate(candidate,bc,parent); validate_candidate(cand); c=cand; write_queue([c])
  except Exception as exc:
   print(f'CONTROLLER_CANDIDATE_REPAIR BC{bc} reason={exc}'); failure=FAILURE_DIR/f'BC{parent}.json'
   if not failure.exists() or not regenerate(bc,parent,failure,s): print(f'CONTROLLER_DECISION HOLD_PROVIDER_REPAIR BC{bc}'); return 0
   cand=load_candidate(candidate,bc,parent); validate_candidate(cand); c=cand; write_queue([cand])
  s['last_bc']=bc; s['iterations']=int(s.get('iterations',0))+1; save(s); print(f'CONTROLLER_CANDIDATE BC{bc} hypothesis_id={c["hypothesis_id"]} GATE {g.name}')
  evidence=ROOT/'research'/f'bc{bc}_validation_result.json'
  rc_eval,_=run([sys.executable,'-m','engine.autonomous_evaluator','--candidate',str(candidate),'--data','data/BTCUSDT_1h.csv','--out',str(evidence)])
  if rc_eval: print(f'CONTROLLER_DECISION HOLD_EVALUATOR BC{bc}'); return 0
  try:
   evaluation=load(evidence,{})
   validate_evaluation(evaluation,c)
  except Exception as exc:
   print(f'CONTROLLER_DECISION HOLD_EVALUATION_CONTRACT BC{bc} reason={exc}'); return 0
  rc,out=run([sys.executable,g.name,str(bc)] if g.name=='audit_bc_fast_gate.py' else [sys.executable,g.name])
  if rc:return rc
  if PROMOTE in out:
   result=oos_once(bc,c)
   if result is None:return 0
   passed=result.get('oos_passed') is True
   decision='OOS_PASS' if passed else 'OOS_FAIL'
   s=transition(s,PROMOTE,bc,c['candidate_hash']); s['history'][-1].update({'hypothesis_id':c['hypothesis_id'],'oos_verdict':decision})
   s['oos_consumed'].append(c['candidate_hash']) if c['candidate_hash'] not in s.get('oos_consumed',[]) else None
   s['terminal']=True; s['terminal_reason']=decision; write_queue([]); save(s)
   print(f'CONTROLLER_DECISION {decision} BC{bc} TERMINAL'); return 0
  if REJECT not in out and 'SPLIT_GATE False' not in out: print(f'CONTROLLER_DECISION BC{bc}_NO_EXPLICIT_DECISION_BLOCKED'); return 5
  write_queue([]); s=transition(s,REJECT,bc,c['candidate_hash']); s['history'][-1].update({'next':'AGENT_HYPOTHESIS','hypothesis_id':c['hypothesis_id']}); save(s)
  failure=FAILURE_DIR/f'BC{bc}.json'
  if not failure.exists(): print(f'CONTROLLER_DECISION HOLD_NO_FAILURE_ANALYSIS BC{bc}'); return 0
  nxt=bc+1
  if not regenerate(nxt,bc,failure,s): print(f'CONTROLLER_DECISION HOLD_PROVIDER_ROUTER BC{nxt}'); return 0
  candidate=json.loads((CANDIDATE_DIR/f'BC{nxt}.json').read_text(encoding='utf-8')); validate_candidate(candidate); write_queue([candidate]); print(f'CONTROLLER_NEXT BC{nxt}')
 print(f'CONTROLLER_SCHEDULER_STOP iterations={MAX} terminal=false'); save(s); return 0
if __name__=='__main__': raise SystemExit(main())
