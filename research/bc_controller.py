from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; STATE=ROOT/'research/bc_lifecycle_state.json'; QUEUE=ROOT/'research/bc_queue.json'; FAILURE_DIR=ROOT/'research/failure_analysis'; CANDIDATE_DIR=ROOT/'research/autonomous_candidates'; PROMOTE='PROMOTE_TO_FUTURE_OOS_TEST'; REJECT='REJECT_BC'; MAX=int(os.environ.get('RESEARCH_MAX_ITERATIONS','8'))
def run(cmd,env=None):
 p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,env=env); out=p.stdout+p.stderr; print(out,end=''); return p.returncode,out
def load(p,d): return json.loads(p.read_text(encoding='utf-8')) if p.exists() else d
def save(s): s['updated_at']=datetime.now(timezone.utc).isoformat(); STATE.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def gate(bc):
 p=ROOT/'audit_bc_fast_gate.py'
 if p.exists(): return p
 p=ROOT/f'audit_bc{bc}_fast_gate.py'; return p if p.exists() else None
def main():
 s=load(STATE,{'history':[],'iterations':0,'last_bc':None,'oos_consumed':[],'terminal':False})
 if s.get('terminal') and not s.get('oos_consumed'): s['terminal']=False; s['terminal_reason']=None; save(s)
 if s.get('terminal'): print('CONTROLLER_DECISION TERMINAL_STATE'); return 0
 if not QUEUE.exists(): print('CONTROLLER_DECISION HOLD_EMPTY_QUEUE'); return 0
 for _ in range(MAX):
  q=load(QUEUE,[])
  if not q: print('CONTROLLER_DECISION HOLD_EMPTY_QUEUE'); return 0
  # Queue is FIFO: only the oldest pending candidate may be evaluated.
  c=q[0]; bc=int(c['bc']); g=gate(bc)
  if not g: print(f'CONTROLLER_DECISION HOLD_NO_GATE BC{bc}'); return 0
  s['last_bc']=bc; s['iterations']=int(s.get('iterations',0))+1; save(s)
  print(f'CONTROLLER_CANDIDATE BC{bc} GATE {g.name}')
  rc,out=run([sys.executable,g.name]+([str(bc)] if g.name=='audit_bc_fast_gate.py' else []))
  if rc: return rc
  if PROMOTE in out: print(f'CONTROLLER_DECISION BC{bc}_PROMOTED'); return 0
  if REJECT not in out and 'SPLIT_GATE False' not in out: print(f'CONTROLLER_DECISION BC{bc}_NO_EXPLICIT_DECISION_BLOCKED'); return 5
  # Remove only the evaluated head. Never delete other pending candidates.
  q=q[1:]; QUEUE.write_text(json.dumps(q,indent=2,sort_keys=True)+'\n',encoding='utf-8')
  s['history'].append({'bc':bc,'decision':'REJECT','next':'AGENT_HYPOTHESIS'}); save(s)
  failure=FAILURE_DIR/f'BC{bc}.json'
  if not failure.exists(): print(f'CONTROLLER_DECISION HOLD_NO_FAILURE_ANALYSIS BC{bc}'); return 0
  nxt=bc+1; output=CANDIDATE_DIR/f'BC{nxt}.json'; env=os.environ.copy(); env.update(RESEARCH_PARENT_BC=str(bc),RESEARCH_FAILURE_ANALYSIS=str(failure),RESEARCH_NEXT_BC=str(nxt),RESEARCH_CANDIDATE_OUTPUT=str(output))
  rc,_=run([sys.executable,'research/provider_router.py'],env=env)
  if rc: return rc
  print(f'CONTROLLER_NEXT BC{nxt}')
 print(f'CONTROLLER_SCHEDULER_STOP iterations={MAX} terminal=false'); save(s); return 0
if __name__=='__main__': raise SystemExit(main())
