from __future__ import annotations
import hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from research.oos_lifecycle import OOSLifecycleError, assert_history_entry_legal, evaluate_oos, lifecycle_event, promotion_event, terminal_reason_from_oos
ROOT=Path(__file__).resolve().parents[1]; STATE=ROOT/'research'/'bc_lifecycle_state.json'; QUEUE=ROOT/'research'/'bc_queue.json'; FAILURE_DIR=ROOT/'research'/'failure_analysis'; CANDIDATE_DIR=ROOT/'research'/'autonomous_candidates'; FREEZE_DIR=ROOT/'research'/'frozen_candidates'; OOS_DIR=ROOT/'research'/'oos'
PROMOTE='PROMOTE_TO_FUTURE_OOS_TEST'; REJECT='REJECT_BC'; MAX=int(os.environ.get('RESEARCH_MAX_ITERATIONS','1')); MAX_RETRIES=int(os.environ.get('RESEARCH_MAX_RESUME_RETRIES','3'))
def run(cmd,env=None):
 p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,env=env); out=p.stdout+p.stderr; print(out,end=''); return p.returncode,out
def load(p,d): return json.loads(p.read_text(encoding='utf-8')) if p.exists() else d
def save(s):
 s['updated_at']=datetime.now(timezone.utc).isoformat()
 STATE.parent.mkdir(parents=True,exist_ok=True)
 tmp=STATE.with_name(STATE.name+'.tmp')
 tmp.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 os.replace(tmp,STATE)
def checkpoint(s,phase,bc=None,error=None):
 s['phase']=phase; s['checkpoint_seq']=int(s.get('checkpoint_seq',0))+1
 if bc is not None: s['current_bc']=int(bc)
 if error is None: s['last_error']=None; s['retry_count']=0
 else: s['last_error']=str(error); s['retry_count']=int(s.get('retry_count',0))+1
 save(s)
def hold(s,reason,bc=None,retryable=True):
 checkpoint(s,'WAIT_RETRY' if retryable else 'HOLD',bc,error=reason); print(f'CONTROLLER_DECISION {reason}{f" BC{bc}" if bc is not None else ""}')
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
 """Generate from a durable discovery frontier, not one disposable survivor.

    Provider selection is currently deterministic by family. Rotate the frontier
    between provider attempts so one rejected/unsupported survivor cannot consume
    the whole BC. The discovery queue is restored byte-for-byte after each attempt.
    Provider-wide failures are held immediately; only translation/contract failures
    advance to the next executable family.
    """
 output=CANDIDATE_DIR/f'BC{bc}.json'; output.parent.mkdir(parents=True,exist_ok=True)
 if output.exists(): output.unlink()
 discovery=ROOT/'research'/'discovery'/'research_queue.json'
 if not discovery.exists(): return False
 original_text=discovery.read_text(encoding='utf-8')
 try:
  payload=json.loads(original_text); raw=payload.get('candidates',[]) if isinstance(payload,dict) else payload
  if not isinstance(raw,list): return False
  families=[]
  for item in raw:
   if not isinstance(item,dict) or not str(item.get('source_url') or '').strip(): continue
   family=str(item.get('family') or '').strip()
   if family and family not in families: families.append(family)
  # Only executable families can reach grounding. Keep the order supplied by discovery.
  executable=[]
  try:
   from research.autonomous_hypothesis import EXECUTABLE_MECHANISM_FAMILIES
   executable=[f for f in families if f in EXECUTABLE_MECHANISM_FAMILIES]
  except Exception:
   executable=families
  if not executable: return False
  used=','.join(used_ids(s)); last_reason=''
  for offset,family in enumerate(executable):
   if output.exists(): output.unlink()
   ordered=[]
   # Put the requested family first while preserving every other survivor and their lineage.
   for f in executable[offset:]+executable[:offset]:
    ordered.extend([x for x in raw if isinstance(x,dict) and str(x.get('family') or '').strip()==f])
   ordered.extend([x for x in raw if isinstance(x,dict) and str(x.get('family') or '').strip() not in executable])
   rotated=dict(payload) if isinstance(payload,dict) else ordered
   if isinstance(payload,dict): rotated['candidates']=ordered
   else: rotated=ordered
   discovery.write_text(json.dumps(rotated,indent=2,sort_keys=True)+'\n',encoding='utf-8')
   env=os.environ.copy(); env.update(RESEARCH_PARENT_BC=str(parent),RESEARCH_FAILURE_ANALYSIS=str(failure),RESEARCH_NEXT_BC=str(bc),RESEARCH_CANDIDATE_OUTPUT=str(output),RESEARCH_USED_HYPOTHESIS_IDS=used,RESEARCH_PRIOR_HYPOTHESES=used)
   rc,out=run([sys.executable,'research/provider_router.py'],env=env)
   if rc==0 and output.exists() and 'PROVIDER_SELECTED' in out:
    print(f'CONTROLLER_TRANSLATION_FRONTIER_SELECTED BC{bc} family={family} offset={offset}')
    return True
   # Provider-wide failures must not be hidden behind a different survivor.
   low=out.lower()
   provider_wide=any(x in low for x in ('provider_not_configured','provider_rate_limited','provider_http_','provider_request_failed','gemini_api_key','401','403'))
   if provider_wide:
    s['provider_failure_reason']=out.strip()[-2000:]; return False
   last_reason=out.strip()[-2000:]
   print(f'CONTROLLER_TRANSLATION_REJECTED BC{bc} family={family} offset={offset}')
  s['translation_frontier_exhausted']=True; s['translation_frontier_last_reason']=last_reason
  return False
 finally:
  try: discovery.write_text(original_text,encoding='utf-8')
  except OSError: pass
def normalize_queue(s):
 q=load(QUEUE,[]); expected=int(s.get('next_bc',int(s.get('last_bc') or 0)+1)); start=int(s.get('campaign_start_bc') or 1)
 if expected<start: expected=start; s['next_bc']=expected; save(s)
 active=[x for x in q if isinstance(x,dict) and int(x.get('bc',-1))==expected and int(x.get('parent_bc',expected-1))==expected-1]
 if len(active)>1: active=active[:1]
 if q!=active: write_queue(active)
 return active
def verify_external_authority(bc,candidate_hash=None):
 contract=os.environ.get('AIOS_CONTRACT_PATH'); permit=os.environ.get('AIOS_PERMIT_PATH'); attestation=os.environ.get('AIOS_ATTESTATION_PATH'); secret=os.environ.get('AIOS_AUTHORITY_SECRET')
 if not all((contract,permit,attestation,secret)) and candidate_hash:
  try:
   from research.aios_oos_authority import provision
   records=provision(bc,candidate_hash); os.environ.update(AIOS_CONTRACT_PATH=records['contract'],AIOS_PERMIT_PATH=records['permit'],AIOS_ATTESTATION_PATH=records['attestation']); contract,permit,attestation=records['contract'],records['permit'],records['attestation']; print(f'AIOS_AUTHORITY_PROVISIONED BC{bc}')
  except Exception as exc: print(f'AIOS_AUTHORITY_HOLD BC{bc} provisioning_failed={exc}'); return False
 if not all((contract,permit,attestation,secret)): print(f'AIOS_AUTHORITY_HOLD BC{bc} missing contract/permit/attestation/secret'); return False
 try:
  from engine.aios_boundary import verify_authority
  result=verify_authority(contract,permit,attestation,secret); expected_task=f'RESEARCH_BC{bc}'
  if result.get('task_id')!=expected_task or result.get('attested') is not True: print(f'AIOS_AUTHORITY_HOLD BC{bc} binding_or_attestation_mismatch'); return False
  if candidate_hash:
   stored=json.loads(Path(contract).read_text(encoding='utf-8'))
   if stored.get('input_digest')!=candidate_hash: print(f'AIOS_AUTHORITY_HOLD BC{bc} candidate_binding_mismatch'); return False
  print(f'AIOS_AUTHORITY_VERIFIED BC{bc} contract_id={result["contract_id"]} issuer={result["issuer"]} attested=true'); return True
 except Exception as exc: print(f'AIOS_AUTHORITY_HOLD BC{bc} reason={exc}'); return False
def append_oos_event(s,event):
 event=dict(event)
 assert_history_entry_legal(event)
 bc=event.get('bc')
 target=event.get('oos_state')
 if bc is None or target is None: raise OOSLifecycleError('OOS_EVENT_REQUIRES_BC_AND_STATE')
 prior=[x for x in s.get('history',[]) if isinstance(x,dict) and int(x.get('bc',-1))==int(bc) and x.get('oos_state')]
 if prior:
  current=prior[-1].get('oos_state')
  try:
   from research.oos_lifecycle import advance
   advance(current,target)
  except Exception as exc:
   raise OOSLifecycleError(f'OOS_HISTORY_TRANSITION_INVALID:{current}->{target}') from exc
 else:
  raise OOSLifecycleError('OOS_EVENT_REQUIRES_PROMOTION_PREDECESSOR')
 for existing in prior:
  if existing.get('oos_state')==target and existing.get('candidate_hash')==event.get('candidate_hash'):
   if existing != event: raise OOSLifecycleError('OOS_EVENT_REPLAY_MISMATCH')
   return existing
 s.setdefault('history',[]).append(event)
 return event

def append_promotion_event(s,bc,candidate_hash):
 existing=[x for x in s.get('history',[]) if isinstance(x,dict) and int(x.get('bc',-1))==int(bc) and x.get('decision')==PROMOTE]
 if existing:
  if len(existing)!=1: raise OOSLifecycleError('DUPLICATE_PROMOTION_EVENTS')
  assert_history_entry_legal(existing[0])
  if existing[0].get('candidate_hash')!=candidate_hash: raise OOSLifecycleError('PROMOTION_CANDIDATE_BINDING_MISMATCH')
  return False
 event=promotion_event()
 event.update({'bc':int(bc),'candidate_hash':candidate_hash})
 assert_history_entry_legal(event)
 s.setdefault('history',[]).append(event)
 return True

def migrate_legacy_state(s):
 history=s.get('history',[])
 if not isinstance(history,list): raise OOSLifecycleError('STATE_HISTORY_SCHEMA_INVALID')
 version=int(s.get('state_schema_version',1))
 if version not in {1,2}: raise OOSLifecycleError('UNSUPPORTED_STATE_SCHEMA_VERSION')
 if version==2:
  for entry in history:
   assert_history_entry_legal(entry)
  return False
 changed=False
 for entry in history:
  if not isinstance(entry,dict): raise OOSLifecycleError('STATE_HISTORY_ENTRY_INVALID')
  verdict=entry.get('oos_verdict')
  if verdict in {'OOS_PASS','OOS_FAIL'}:
   entry['legacy_oos_verdict']=verdict
   entry['oos_verdict']=None
   entry['oos_executed']=False
   entry['oos_state']='UNKNOWN'
   entry['semantic_status']='LEGACY_UNVERIFIED_OOS'
   entry['migration_id']='OOS_CANONICAL_V1'
   changed=True
 if s.get('terminal_reason') in {'OOS_PASS','OOS_FAIL'} and not s.get('terminal'):
  s['legacy_terminal_reason']=s['terminal_reason']; s['terminal_reason']=None; changed=True
 if s.get('campaign_terminal_reason') in {'OOS_PASS','OOS_FAIL'} and not s.get('terminal'):
  s['legacy_campaign_terminal_reason']=s['campaign_terminal_reason']; s['campaign_terminal_reason']=None; changed=True
 if changed:
  s.setdefault('state_migrations',[]).append({'migration_id':'OOS_CANONICAL_V1','status':'APPLIED','reason':'legacy OOS verdicts demoted to UNKNOWN until execution/receipt/evaluation evidence exists'})
  s['state_schema_version']=2
 else:
  s['state_schema_version']=2
 return changed

def authorized_state(s):
 caps=s.get('capabilities',[])
 if not isinstance(caps,list) or any(str(x)!='research' for x in caps): print('AIOS_STATE_HOLD undeclared capability in durable controller state'); return False
 return True
def verify_oos_receipt(bc,candidate_hash,result,receipt_path):
 if not isinstance(result,dict) or result.get('bc')!=bc or result.get('candidate_hash')!=candidate_hash or result.get('oos_executed') is not True or result.get('oos_selection_used') is not False or not receipt_path.exists(): return False
 try: receipt=load(receipt_path,{})
 except Exception: return False
 if receipt.get('receipt_type')!='OOS_EXECUTION_RECEIPT' or receipt.get('schema_version')!=1 or receipt.get('bc')!=bc or receipt.get('candidate_hash')!=candidate_hash or receipt.get('oos_executed') is not True or receipt.get('oos_selection_used') is not False: return False
 if receipt.get('oos_passed') is not result.get('oos_passed') or receipt.get('metrics')!=result.get('metrics'): return False
 if receipt.get('dataset_sha256')!=result.get('dataset',{}).get('sha256') or receipt.get('protocol_sha256')!=result.get('protocol_sha256'): return False
 try: return receipt.get('result_sha256')==hashlib.sha256((OOS_DIR/f'BC{bc}_oos_result.json').read_bytes()).hexdigest()
 except OSError: return False
def write_oos_failure(bc,parent,candidate,result):
 path=FAILURE_DIR/f'BC{bc}.json'; FAILURE_DIR.mkdir(parents=True,exist_ok=True)
 if path.exists(): return path
 payload={'bc':bc,'parent_bc':parent,'decision':'REJECT','reason':'OOS_FAILED','hypothesis_id':candidate.get('hypothesis_id'),'candidate_hash':candidate.get('candidate_hash'),'conceptual_change':candidate.get('conceptual_change'),'evidence_sources':candidate.get('evidence_sources'),'validation_summary':result.get('metrics'),'oos_verdict':'OOS_FAIL','oos_selection_used':False,'action':'reject candidate and require a distinct next hypothesis'}
 path.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8'); return path
def oos_once(bc,candidate):
 candidate_hash=candidate['candidate_hash']
 if not verify_external_authority(bc,candidate_hash): return None
 protocol=ROOT/'research'/'oos_protocol.json'; out=OOS_DIR/f'BC{bc}_oos_result.json'; receipt=OOS_DIR/f'BC{bc}_oos_result_receipt.json'; freeze=FREEZE_DIR/f'BC{bc}.json'
 if not protocol.exists(): print('OOS_HOLD_PROTOCOL_MISSING'); return None
 FREEZE_DIR.mkdir(parents=True,exist_ok=True); OOS_DIR.mkdir(parents=True,exist_ok=True)
 if freeze.exists():
  frozen=load(freeze,{})
  if frozen.get('candidate_hash')!=candidate_hash: print('OOS_HOLD_FROZEN_HASH_MISMATCH'); return None
 else: freeze.write_text(json.dumps(candidate,indent=2)+'\n',encoding='utf-8')
 if out.exists():
  result=load(out,{})
  if not verify_oos_receipt(bc,candidate_hash,result,receipt): print('OOS_HOLD_EXISTING_ARTIFACT_OR_RECEIPT_INVALID'); return None
  return result
 rc,_=run([sys.executable,'-m','engine.oos_runner','--candidate',str(freeze),'--data','data/BTCUSDT_1h.csv','--protocol','research/oos_protocol.json','--out',str(out)])
 if rc or not out.exists() or not verify_oos_receipt(bc,candidate_hash,load(out,{}),receipt): print(f'CONTROLLER_DECISION HOLD_OOS_EXECUTOR_OR_RECEIPT BC{bc}'); return None
 return load(out,{})
def epoch_seed_failure(parent,start):
 raw=os.environ.get('RESEARCH_EPOCH_SEED_FAILURE','').strip()
 if not raw or parent!=start-1: return None
 try:
  p=Path(raw).resolve(); expected=(ROOT/'research'/'.epoch_seed_failure.json').resolve()
  if p!=expected or not p.exists(): return None
  seed=load(p,{})
  if seed.get('kind')!='epoch_seed_failure' or seed.get('decision')!='SEED_EPOCH' or int(seed.get('parent_bc',-1))!=parent or int(seed.get('epoch_start_bc',-1))!=start or seed.get('research_evidence') is not False or seed.get('repair_context') is not True: return None
  print(f'CONTROLLER_EPOCH_SEED_CONSUMED parent=BC{parent} start=BC{start} evidence=false repair_context=true'); return p
 except (OSError,TypeError,ValueError): return None
def main():
 s=load(STATE,{'history':[],'iterations':0,'last_bc':None,'next_bc':1,'oos_consumed':[],'terminal':False,'phase':'OBSERVE','retry_count':0})
 try:
  if migrate_legacy_state(s): save(s)
 except OOSLifecycleError as exc:
  checkpoint(s,'HOLD',error=str(exc)); return 4
 for entry in s.get('history',[]): assert_history_entry_legal(entry)
 if not authorized_state(s): checkpoint(s,'HOLD',error='persisted controller state contains undeclared capability'); return 4
 if s.get('terminal'):
  bc=int(s.get('current_bc') or s.get('last_bc') or 0)
  ev=s.get('oos_evaluation') or {}
  if bc and ev.get('bc')==bc and ev.get('oos_verdict')=='OOS_PASS' and verify_external_authority(bc):
   print('CONTROLLER_DECISION TERMINAL_STATE_AUTHORIZED'); return 0
  checkpoint(s,'HOLD',bc,error='persisted terminal state lacks bound OOS_PASS evaluation or valid authority attestation'); return 3
  checkpoint(s,'HOLD',bc,error='persisted terminal state lacks valid external authority attestation'); return 3
 checkpoint(s,'OBSERVE',s.get('current_bc')); q=normalize_queue(s)
 if not q:
  expected=int(s.get('next_bc',int(s.get('last_bc') or 0)+1)); parent=expected-1
  if parent==0: return hold(s,'HOLD_NO_REGISTERED_BASELINE',expected,retryable=False)
  failure=FAILURE_DIR/f'BC{parent}.json'
  if not failure.exists():
   failure=epoch_seed_failure(parent,int(s.get('campaign_start_bc') or 1))
   if failure is None: return hold(s,'HOLD_NO_FAILURE_ANALYSIS',parent,retryable=False)
  checkpoint(s,'DECIDE',expected)
  if not regenerate(expected,parent,failure,s):
   if s.get('provider_failure_reason'): return hold(s,'HOLD_PROVIDER_'+s['provider_failure_reason'][-400:].replace('\n',' '),expected)
   if s.get('translation_frontier_exhausted'): return hold(s,'HOLD_TRANSLATION_FRONTIER_EXHAUSTED',expected,retryable=False)
   return hold(s,'HOLD_PROVIDER_ROUTER',expected)
  candidate=json.loads((CANDIDATE_DIR/f'BC{expected}.json').read_text(encoding='utf-8')); write_queue([candidate]); checkpoint(s,'PERSISTED',expected); print(f'CONTROLLER_CANDIDATE_QUEUED BC{expected}'); return 0
 q=normalize_queue(s)
 if not q: return hold(s,'HOLD_EMPTY_QUEUE',s.get('next_bc'))
 c=q[0]; bc=int(c['bc']); parent=int(c.get('parent_bc',bc-1)); candidate=CANDIDATE_DIR/f'BC{bc}.json'; g=gate(bc)
 if bc<int(s.get('campaign_start_bc') or 1): return hold(s,f'HOLD_PRE_EPOCH_BC_{bc}',bc,retryable=False)
 if not g: return hold(s,'HOLD_NO_GATE',bc,retryable=False)
 checkpoint(s,'OBSERVE',bc)
 try:
  from research.autonomous_hypothesis import load_candidate
  c=load_candidate(candidate,bc,parent); write_queue([c])
 except Exception as exc:
  print(f'CONTROLLER_CANDIDATE_REPAIR BC{bc} reason={exc}'); failure=FAILURE_DIR/f'BC{parent}.json'
  if not failure.exists() or not regenerate(bc,parent,failure,s): return hold(s,'HOLD_PROVIDER_REPAIR',bc)
  from research.autonomous_hypothesis import load_candidate
  c=load_candidate(candidate,bc,parent); write_queue([c])
 s['last_bc']=bc; s['iterations']=int(s.get('iterations',0))+1; checkpoint(s,'ACT',bc); print(f'CONTROLLER_CANDIDATE BC{bc} hypothesis_id={c["hypothesis_id"]} GATE {g.name}')
 evidence=ROOT/'research'/f'bc{bc}_validation_result.json'; rc_eval,_=run([sys.executable,'-m','engine.autonomous_evaluator','--candidate',str(candidate),'--data','data/BTCUSDT_1h.csv','--out',str(evidence)])
 if rc_eval: return hold(s,'HOLD_EVALUATOR',bc)
 checkpoint(s,'VERIFY',bc); rc,out=run([sys.executable,g.name,str(bc)] if g.name=='audit_bc_fast_gate.py' else [sys.executable,g.name])
 if rc: return rc
 if PROMOTE in out:
  try:
   append_promotion_event(s,bc,c['candidate_hash'])
   append_oos_event(s,lifecycle_event('OOS_AUTHORIZED',bc=bc,candidate_hash=c['candidate_hash']))
   append_oos_event(s,lifecycle_event('OOS_DISPATCHED',bc=bc,candidate_hash=c['candidate_hash']))
  except OOSLifecycleError as exc:
   return hold(s,'HOLD_OOS_HISTORY_INTEGRITY:'+str(exc),bc,retryable=False)
  checkpoint(s,'FREEZE_OOS',bc)
  result=oos_once(bc,c)
  if result is None:
   append_oos_event(s,{'bc':bc,'candidate_hash':c['candidate_hash'],'oos_state':'UNKNOWN','oos_verdict':None,'oos_executed':False})
   return hold(s,'HOLD_OOS_EXECUTOR_OR_AUTHORITY',bc)
  receipt=load(OOS_DIR/f'BC{bc}_oos_result_receipt.json',{})
  append_oos_event(s,lifecycle_event('OOS_EXECUTED',bc=bc,candidate_hash=c['candidate_hash']))
  checkpoint(s,'OOS_EXECUTED',bc)
  append_oos_event(s,{'bc':bc,'candidate_hash':c['candidate_hash'],'oos_state':'OOS_RECEIPT','oos_verdict':None,'oos_executed':True,'receipt_type':receipt.get('receipt_type'),'receipt_schema_version':receipt.get('schema_version'),'receipt_id':receipt.get('result_sha256')})
  checkpoint(s,'OOS_RECEIPT',bc)
  try:
   evaluation=evaluate_oos(result,receipt)
   evaluation_entry={'bc':bc,'candidate_hash':c['candidate_hash'],**evaluation}
   assert_history_entry_legal(evaluation_entry)
  except OOSLifecycleError as exc:
   return hold(s,'HOLD_OOS_EVALUATION_INTEGRITY:'+str(exc),bc,retryable=False)
  s['oos_evaluation']=evaluation_entry
  append_oos_event(s,evaluation_entry)
  checkpoint(s,'OOS_EVALUATED',bc)
  decision=evaluation['oos_verdict']
  if c['candidate_hash'] not in s.get('oos_consumed',[]): s.setdefault('oos_consumed',[]).append(c['candidate_hash'])
  write_queue([])
  if decision=='OOS_PASS':
   s['terminal']=True
   s['terminal_reason']=terminal_reason_from_oos(result,receipt)
   s['next_bc']=bc+1
   checkpoint(s,'TERMINAL',bc)
   print(f'CONTROLLER_DECISION {s["terminal_reason"]} BC{bc} TERMINAL')
   return 0
  write_oos_failure(bc,parent,c,result)
  s['terminal']=False
  s['terminal_reason']=terminal_reason_from_oos(result,receipt)
  s['next_bc']=bc+1
  checkpoint(s,'PERSISTED',bc)
  print(f'CONTROLLER_NEXT_AFTER_OOS_FAIL BC{bc+1}')
  return 0
 if REJECT not in out and 'SPLIT_GATE False' not in out:
  checkpoint(s,'HOLD',bc,error='NO_EXPLICIT_DECISION'); print(f'CONTROLLER_DECISION BC{bc}_NO_EXPLICIT_DECISION_BLOCKED'); return 5
 write_queue([]); s['history'].append({'bc':bc,'decision':REJECT,'next':'AGENT_HYPOTHESIS','hypothesis_id':c['hypothesis_id'],'candidate_hash':c.get('candidate_hash')}); s['next_bc']=bc+1; checkpoint(s,'PERSISTED',bc); failure=FAILURE_DIR/f'BC{bc}.json'
 if not failure.exists(): return hold(s,'HOLD_NO_FAILURE_ANALYSIS',bc,retryable=False)
 nxt=bc+1; checkpoint(s,'DECIDE',nxt)
 if not regenerate(nxt,bc,failure,s):
  if s.get('provider_failure_reason'): return hold(s,'HOLD_PROVIDER_'+s['provider_failure_reason'][-400:].replace('\n',' '),nxt)
  if s.get('translation_frontier_exhausted'): return hold(s,'HOLD_TRANSLATION_FRONTIER_EXHAUSTED',nxt,retryable=False)
  return hold(s,'HOLD_PROVIDER_ROUTER',nxt)
 candidate=json.loads((CANDIDATE_DIR/f'BC{nxt}.json').read_text(encoding='utf-8')); write_queue([candidate]); checkpoint(s,'PERSISTED',nxt); print(f'CONTROLLER_NEXT BC{nxt}')
 print(f'CONTROLLER_SCHEDULER_STOP iterations={MAX} terminal=false'); checkpoint(s,'YIELD',s.get('next_bc')); print('CONTROLLER_AUTO_RESUME scheduler_yield'); return 0
if __name__=='__main__': raise SystemExit(main())