#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
QUEUE=ROOT/'research/bc_queue.json'; STATE=ROOT/'research/bc_lifecycle_state.json'
PROMOTE={'PROMOTE_TO_FUTURE_OOS_TEST'}
def load(p,d): return json.loads(p.read_text()) if p.exists() else d
def save(p,v): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,indent=2))
def run(name,script,state):
 print('RUN',name,script); p=subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,text=True,capture_output=True); out=p.stdout+('\n'+p.stderr if p.stderr else ''); print(out,end='' if out.endswith('\n') else '\n')
 if p.returncode: state.update(status='BLOCKED',blocked_on=name,reason='audit_failed'); save(STATE,state); return p.returncode,None
 d=next((x.removeprefix('DECISION ').strip() for x in reversed(out.splitlines()) if x.startswith('DECISION ')),None)
 state.setdefault('completed',[])
 if name not in state['completed']: state['completed'].append(name)
 state['last_stage']=name
 if d: state['last_decision']=d
 save(STATE,state); return 0,d
def failure_chain(candidate,q,state,done):
 for x in q.get('failure_analysis',{}).get(candidate,[]):
  if x['name'] in done: continue
  rc,_=run(x['name'],x['audit_script'],state)
  if rc:return rc
  done.add(x['name'])
 return 0
def main():
 q=load(QUEUE,{}); s=load(STATE,{'schema_version':3,'completed':[],'status':'READY'}); done=set(s.get('completed',[])); cs=q.get('candidates',[])
 pending=[x for x in cs if x['name'] not in done]
 if not pending:
  candidate=s.get('blocked_on') or 'BC5'
  if s.get('last_decision','').startswith('REJECT_') or s.get('status') in {'FAILURE_ANALYSIS_REQUIRED','HYPOTHESIS_REGISTRATION_REQUIRED','NO_PENDING_REGISTERED_CANDIDATE'}:
   rc=failure_chain(candidate,q,s,done)
   if rc:return rc
   rc,d=run('NEXT_HYPOTHESIS_DISCOVERY','audit_candidate_discovery.py',s)
   if rc:return rc
   s['status']='NO_VALIDATED_NEXT_HYPOTHESIS' if d=='NO_VALIDATED_NEXT_HYPOTHESIS' else 'HYPOTHESIS_REGISTRATION_REQUIRED'
   save(STATE,s); print('LIFECYCLE_STOP',s['status']); return 0
 for x in pending:
  rc,d=run(x['name'],x['audit_script'],s)
  if rc:return rc
  done.add(x['name'])
  if d in PROMOTE:s.update(status='FROZEN_OOS_REQUIRED',blocked_on=x['name']);save(STATE,s);print('LIFECYCLE_STOP',s['status']);return 0
  if d and d.startswith('REJECT_'):
   rc=failure_chain(x['name'],q,s,done)
   if rc:return rc
   rc,nd=run('NEXT_HYPOTHESIS_DISCOVERY','audit_candidate_discovery.py',s)
   if rc:return rc
   s['status']='NO_VALIDATED_NEXT_HYPOTHESIS' if nd=='NO_VALIDATED_NEXT_HYPOTHESIS' else 'HYPOTHESIS_REGISTRATION_REQUIRED';save(STATE,s);print('LIFECYCLE_STOP',s['status']);return 0
 s['status']='NO_PENDING_REGISTERED_CANDIDATE';save(STATE,s);print('LIFECYCLE_STOP',s['status']);return 0
if __name__=='__main__': raise SystemExit(main())
