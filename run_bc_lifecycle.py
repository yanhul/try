#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent; QUEUE=ROOT/'research/bc_queue.json'; STATE=ROOT/'research/bc_lifecycle_state.json'; PROMOTE={'PROMOTE_TO_FUTURE_OOS_TEST'}
def load(p,d): return json.loads(p.read_text()) if p.exists() else d
def save(p,v): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,indent=2))
def run(name,script,s):
 print('RUN',name,script); p=subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,text=True,capture_output=True); out=p.stdout+('\n'+p.stderr if p.stderr else ''); print(out,end='' if out.endswith('\n') else '\n')
 if p.returncode: s.update(status='BLOCKED',blocked_on=name,reason='audit_failed'); save(STATE,s); return p.returncode,None
 d=next((x.removeprefix('DECISION ').strip() for x in reversed(out.splitlines()) if x.startswith('DECISION ')),None); s.setdefault('completed',[]); s['completed'].append(name) if name not in s['completed'] else None; s['last_stage']=name; s['last_decision']=d if d else s.get('last_decision'); save(STATE,s); return 0,d
def main():
 q=load(QUEUE,{}); s=load(STATE,{'schema_version':4,'completed':[],'status':'READY'}); done=set(s.get('completed',[])); pending=[x for x in q.get('candidates',[]) if x['name'] not in done]
 if not pending:
  last=s.get('last_candidate')
  if last and s.get('last_decision','').startswith('REJECT_'):
   for x in q.get('failure_analysis',{}).get(last,[]):
    if x['name'] not in done:
     rc,_=run(x['name'],x['audit_script'],s)
     if rc:return rc
     done.add(x['name'])
  rc,d=run('NEXT_HYPOTHESIS_DISCOVERY','audit_candidate_discovery.py',s)
  if rc:return rc
  s['status']='NO_VALIDATED_NEXT_HYPOTHESIS' if d=='NO_VALIDATED_NEXT_HYPOTHESIS' else ('HYPOTHESIS_REGISTRATION_REQUIRED' if d else 'BLOCKED'); save(STATE,s); print('LIFECYCLE_STOP',s['status']); return 0
 for x in pending:
  s['last_candidate']=x['name']; save(STATE,s); rc,d=run(x['name'],x['audit_script'],s)
  if rc:return rc
  done.add(x['name'])
  if d in PROMOTE: s.update(status='FROZEN_OOS_REQUIRED',blocked_on=x['name']); save(STATE,s); print('LIFECYCLE_STOP',s['status']); return 0
  if d and d.startswith('REJECT_'):
   for a in q.get('failure_analysis',{}).get(x['name'],[]):
    if a['name'] not in done:
     rc,_=run(a['name'],a['audit_script'],s)
     if rc:return rc
     done.add(a['name'])
   return main()
 return main()
if __name__=='__main__': raise SystemExit(main())
