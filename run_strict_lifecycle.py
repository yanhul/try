#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATE=ROOT/'research/lifecycle_state.json'; PENDING=ROOT/'research/bc_pending_candidate.json'; QUEUE=ROOT/'research/bc_queue.json'
DISCOVERY=ROOT/'audit_candidate_discovery.py'; CANDIDATE_AUDIT=ROOT/'audit_candidate_feature.py'
FAILURE_AUDITS=[ROOT/'audit_bc4_1_failure_decomposition.py',ROOT/'audit_bc4_2_signal_quality.py']
MAX_ITERATIONS=int(os.environ.get('STRICT_MAX_ITERATIONS','50'))

def load_state():
    if not STATE.exists(): return {'version':1,'audited_candidates':[],'history':[]}
    return json.loads(STATE.read_text(encoding='utf-8'))
def save_state(s):
    STATE.parent.mkdir(parents=True,exist_ok=True); STATE.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def run_script(path):
    p=subprocess.run([sys.executable,str(path)],cwd=ROOT,text=True,capture_output=True); out=p.stdout
    if p.stderr: out+=("\n" if out and not out.endswith("\n") else "")+p.stderr
    print(out,end='' if out.endswith('\n') else '\n'); return p.returncode,out
def decision(text):
    for line in reversed(text.splitlines()):
        if line.startswith('DECISION '): return line[9:].strip()
        if line.startswith('LIFECYCLE_STOP '): return line[15:].strip()
    return None
def append_history(s,item):
    s.setdefault('history',[]).append(item); s['history']=s['history'][-200:]
def failure_analysis(s,name):
    print('FAILURE_ANALYSIS_REQUIRED',name)
    for audit in FAILURE_AUDITS:
        rc,_=run_script(audit)
        if rc:return rc
    return 0
def freeze_bc5(s):
    rc,out=run_script(ROOT/'audit_bc5_fast_gate.py')
    if rc:return rc
    d=decision(out)
    if d is None: print('LIFECYCLE_STOP BC5_GATE_NO_DECISION'); return 2
    append_history(s,{'candidate':'BC5','decision':d}); s.setdefault('audited_candidates',[]).append('BC5')
    if not d.startswith('PROMOTE_TO_FUTURE_OOS_TEST'):
        save_state(s); return failure_analysis(s,'BC5')
    definition={'candidate':'BC5','feature':'sweep_signed_body','single_change':'liquidity sweep candle body must align with sweep direction','rule':'bullish sweep close >= open; bearish sweep close <= open','selection_data':'IS+VALIDATION_ONLY','oos_touched':False,'source_gate':'audit_bc5_fast_gate.py'}
    raw=json.dumps(definition,sort_keys=True,separators=(',',':')).encode(); definition['frozen_parameter_hash']=hashlib.sha256(raw).hexdigest()
    PENDING.write_text(json.dumps(definition,indent=2,sort_keys=True)+'\n',encoding='utf-8'); s['frozen_candidate']=definition; save_state(s)
    print('FROZEN_CANDIDATE_READY',{'candidate':'BC5','hash':definition['frozen_parameter_hash']}); print('LIFECYCLE_TERMINAL FROZEN_CANDIDATE_READY_FOR_OOS'); return 0
def main():
    s=load_state(); print('STRICT_LIFECYCLE_STATUS',{'oos_selection':False,'no_automatic_hypothesis_invention':True,'max_iterations':MAX_ITERATIONS})
    q=json.loads(QUEUE.read_text(encoding='utf-8')) if QUEUE.exists() else {}; registered={x.get('name'):x.get('audit_script') for x in q.get('candidates',[])}
    if 'BC5' in registered and 'BC5' not in s.get('audited_candidates',[]): return freeze_bc5(s)
    for iteration in range(1,MAX_ITERATIONS+1):
        print('LIFECYCLE_ITERATION',iteration); rc,out=run_script(DISCOVERY)
        if rc:return rc
        d=decision(out)
        if d is None: print('LIFECYCLE_STOP DISCOVERY_NO_DECISION'); return 2
        if d.startswith('REGISTERED_NEXT_CANDIDATE'):
            if not PENDING.exists(): print('LIFECYCLE_STOP DISCOVERY_CLAIMED_CANDIDATE_WITHOUT_PENDING'); return 2
            rc,out=run_script(CANDIDATE_AUDIT)
            if rc:return rc
            cd=decision(out)
            if cd is None: print('LIFECYCLE_STOP CANDIDATE_AUDIT_NO_DECISION'); return 2
            name='BC6_'+json.loads(PENDING.read_text(encoding='utf-8'))['feature']; s.setdefault('audited_candidates',[]).append(name); append_history(s,{'iteration':iteration,'candidate':name,'decision':cd}); save_state(s)
            if cd.startswith('PROMOTE_TO_FUTURE_OOS_TEST'): print('LIFECYCLE_TERMINAL FROZEN_CANDIDATE_READY_FOR_OOS'); return 0
            PENDING.unlink(); rc=failure_analysis(s,name)
            if rc:return rc
            continue
        if d=='NO_VALIDATED_NEXT_HYPOTHESIS': print('LIFECYCLE_TERMINAL EXHAUSTED'); return 0
        if d.startswith('LIFECYCLE_STOP'): print('LIFECYCLE_TERMINAL',d); return 0
        print('LIFECYCLE_STOP UNEXPECTED_DECISION',d); return 2
    print('LIFECYCLE_TERMINAL RESEARCH_BUDGET_EXHAUSTED',{'max_iterations':MAX_ITERATIONS}); return 0
if __name__=='__main__': raise SystemExit(main())
