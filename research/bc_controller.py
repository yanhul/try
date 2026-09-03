from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; STATE=ROOT/'research'/'bc_lifecycle_state.json'; QUEUE=ROOT/'research'/'bc_queue.json'; FAILURE_DIR=ROOT/'research'/'failure_analysis'; CANDIDATE_DIR=ROOT/'research'/'autonomous_candidates'; FREEZE_DIR=ROOT/'research'/'frozen_candidates'; OOS_DIR=ROOT/'research'/'oos'
PROMOTE='PROMOTE_TO_FUTURE_OOS_TEST'; REJECT='REJECT_BC'; MAX=int(os.environ.get('RESEARCH_MAX_ITERATIONS','8')); MAX_RETRIES=int(os.environ.get('RESEARCH_MAX_RESUME_RETRIES','3'))
def run(cmd,env=None):
 p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,env=env); out=p.stdout+p.stderr; print(out,end=''); return p.returncode,out
def load(p,d): return json.loads(p.read_text(encoding='utf-8')) if p.exists() else d
def save(s): s['updated_at']=datetime.now(timezone.utc).isoformat(); STATE.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def checkpoint(s,phase,bc=None,error=None):
 s['phase']=phase; s['checkpoint_seq']=int(s.get('checkpoint_seq',0))+1
 if bc is not None: s['current_bc']=int(bc)
 if error is None: s['last_error']=None; s['retry_count']=0
 else: s['last_error']=str(error); s['retry_count']=int(s.get('retry_count',0))+1
 save(s)
def hold(s,reason,bc=None,retryable=True):
 checkpoint(s,'WAIT_RETRY' if retryable else 'HOLD',bc,error=reason); suffix=f' BC{bc}' if bc is not None else ''; print(f'CONTROLLER_DECISION {reason}{suffix}')
 if retryable and int(s.get('retry_count',0))<=MAX_RETRIES: print(f'CONTROLLER_AUTO_RESUME retry={s["retry_count"]}/{MAX_RETRIES}')
 else: print(f'CONTROLLER_MANUAL_HOLD retry={s.get("retry_count",0)}/{MAX_RETRIES}')
 return 0
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
 if q!=active: write_queue(active)
 return active
def verify_external_authority(bc):
 contract=os.environ.get('AIOS_CONTRACT_PATH'); permit=os.environ.get('AIOS_PERMIT_PATH'); attestation=os.environ.get('AIOS_ATTESTATION_PATH'); secret=os.environ.get('AIOS_AUTHORITY_SECRET')
 if not all((contract,permit,attestation,secret)):
  print(f'AIOS_AUTHORITY_HOLD BC{bc} missing contract/permit/attestation/secret'); return False
 try:
  from engine.aios_boundary import verify_authority
  result=verify_authority(contract,permit,attestation,secret); expected_task=f'RESEARCH_BC{bc}'
  if result.get('task_id')!=expected_task or result.get('attested') is not True:
   print(f'AIOS_AUTHORITY_HOLD BC{bc} binding_or_attestation_mismatch'); return False
  print(f'AIOS_AUTHORITY_VERIFIED BC{bc} contract_id={result["contract_id"]} issuer={result["issuer"]} attested=true'); return True
 except Exception as exc:
  print(f'AIOS_AUTHORITY_HOLD BC{bc} reason={exc}'); return False
def oos_once(bc,candidate):
 if not verify_external_authority(bc): return None
 protocol=ROOT/'research'/'oos_protocol.json'; out=OOS_DIR/f'BC{bc}_oos_result.json'; freeze=FREEZE_DIR/f'BC{bc}.json'
 if not protocol.exists(): print('OOS_HOLD_PROTOCOL_MISSING'); return None
 FREEZE_DIR.mkdir(parents=True,exist_ok=True); OOS_DIR.mkdir(parents=True,exist_ok=True); candidate_hash=candidate['candidate_hash']
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
 s=load(STATE,{'history':[],'iterations':0,'last_bc':None,'next_bc':1,'oos_consumed':[],'terminal':False,'phase':'OBSERVE','retry_count':0})
 if s.get('terminal'): print('CONTROLLER_DECISION TERMINAL_STATE'); return 0
 checkpoint(s,'OBSERVE',s.get('current_bc')); q=normalize_queue(s)
 if not q:
  expected=int(s.get('next_bc',int(s.get('last_bc') or 0)+1)); parent=expected-1
  if parent==0: return hold(s,'HOLD_NO_REGISTERED_BASELINE',expected,retryable=False)
  failure=FAILURE_DIR/f'BC{parent}.json'
  if not failure.exists(): return hold(s,'HOLD_NO_FAILURE_ANALYSIS',parent,retryable=False)
  checkpoint(s,'DECIDE',expected)
  if not regenerate(expected,parent,failure,s): return hold(s,'HOLD_PROVIDER_ROUTER',expected)
  candidate=json.loads((CANDIDATE_DIR/f'BC{expected}.json').read_text(encoding='utf-8')); write_queue([candidate]); q=[candidate]; checkpoint(s,'PERSISTED',expected)
 for _ in range(MAX):
  q=normalize_queue(s)
  if not q: return hold(s,'HOLD_EMPTY_QUEUE',s.get('next_bc'))
  c=q[0]; bc=int(c['bc']); parent=int(c.get('parent_bc',bc-1)); candidate=CANDIDATE_DIR/f'BC{bc}.json'; g=gate(bc)
  if not g: return hold(s,'HOLD_NO_GATE',bc,retryable=False)
  checkpoint(s,'OBSERVE',bc)
  try:
   from autonomous_hypothesis import load_candidate
   cand=load_candidate(candidate,bc,parent); c=cand; write_queue([cand])
  except Exception as exc:
   print(f'CONTROLLER_CANDIDATE_REPAIR BC{bc} reason={exc}'); failure=FAILURE_DIR/f'BC{parent}.json'
   if not failure.exists() or not regenerate(bc,parent,failure,s): return hold(s,'HOLD_PROVIDER_REPAIR',bc)
   cand=load_candidate(candidate,bc,parent); write_queue([cand]); c=cand
  s['last_bc']=bc; s['iterations']=int(s.get('iterations',0))+1; checkpoint(s,'ACT',bc); print(f'CONTROLLER_CANDIDATE BC{bc} hypothesis_id={c["hypothesis_id"]} GATE {g.name}')
  evidence=ROOT/'research'/f'bc{bc}_validation_result.json'; rc_eval,_=run([sys.executable,'-m','engine.autonomous_evaluator','--candidate',str(candidate),'--data','data/BTCUSDT_1h.csv','--out',str(evidence)])
  if rc_eval: return hold(s,'HOLD_EVALUATOR',bc)
  checkpoint(s,'VERIFY',bc); rc,out=run([sys.executable,g.name,str(bc)] if g.name=='audit_bc_fast_gate.py' else [sys.executable,g.name])
  if rc: return rc
  if PROMOTE in out:
   checkpoint(s,'FREEZE_OOS',bc); result=oos_once(bc,c)
   if result is None: return hold(s,'HOLD_OOS_EXECUTOR_OR_AUTHORITY',bc)
   passed=result.get('oos_passed') is True; decision='OOS_PASS' if passed else 'OOS_FAIL'; s['history'].append({'bc':bc,'decision':'PROMOTE_TO_FUTURE_OOS_TEST','hypothesis_id':c['hypothesis_id'],'candidate_hash':c['candidate_hash'],'oos_verdict':decision})
   if c['candidate_hash'] not in s.get('oos_consumed',[]): s.setdefault('oos_consumed',[]).append(c['candidate_hash'])
   s['terminal']=True; s['terminal_reason']=decision; s['next_bc']=bc+1; write_queue([]); checkpoint(s,'TERMINAL',bc); print(f'CONTROLLER_DECISION {decision} BC{bc} TERMINAL'); return 0
  if REJECT not in out and 'SPLIT_GATE False' not in out: checkpoint(s,'HOLD',bc,error='NO_EXPLICIT_DECISION'); print(f'CONTROLLER_DECISION BC{bc}_NO_EXPLICIT_DECISION_BLOCKED'); return 5
  write_queue([]); s['history'].append({'bc':bc,'decision':'REJECT','next':'AGENT_HYPOTHESIS','hypothesis_id':c['hypothesis_id']}); s['next_bc']=bc+1; checkpoint(s,'PERSISTED',bc); failure=FAILURE_DIR/f'BC{bc}.json'
  if not failure.exists(): return hold(s,'HOLD_NO_FAILURE_ANALYSIS',bc,retryable=False)
  nxt=bc+1; checkpoint(s,'DECIDE',nxt)
  if not regenerate(nxt,bc,failure,s): return hold(s,'HOLD_PROVIDER_ROUTER',nxt)
  candidate=json.loads((CANDIDATE_DIR/f'BC{nxt}.json').read_text(encoding='utf-8')); write_queue([candidate]); checkpoint(s,'PERSISTED',nxt); print(f'CONTROLLER_NEXT BC{nxt}')
 print(f'CONTROLLER_SCHEDULER_STOP iterations={MAX} terminal=false'); checkpoint(s,'YIELD',s.get('next_bc')); print('CONTROLLER_AUTO_RESUME scheduler_yield'); return 0
if __name__=='__main__': raise SystemExit(main())