from __future__ import annotations
import ast,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent; DIAGNOSTIC=ROOT/'audit_bc4_2_signal_quality.py'; PENDING=ROOT/'research/bc_pending_candidate.json'; QUEUE=ROOT/'research/bc_queue.json'
FEATURES={'entry_close_location','entry_signed_body','sweep_close_location','sweep_signed_body','fast_entry_le_1bar','fast_entry_le_2bar','fast_entry_le_3bar'}
ALREADY_AUDITED={'sweep_signed_body'}

def main():
 p=subprocess.run([sys.executable,str(DIAGNOSTIC)],cwd=ROOT,text=True,capture_output=True); out=p.stdout+(('\n'+p.stderr) if p.stderr else ''); print(out,end='' if out.endswith('\n') else '\n')
 if p.returncode:return p.returncode
 blocks={}; current=None
 for line in out.splitlines():
  if line.startswith('SPLIT_LABEL '): current=line.split()[2]; blocks[current]={}
  elif line.startswith('FEATURE ') and current:
   head,rest=line.split(' PASS ',1); name=head.split()[1]; ptxt,ftxt=rest.split(' FAIL ',1)
   try: blocks[current][name]=(ast.literal_eval(ptxt),ast.literal_eval(ftxt))
   except (ValueError,SyntaxError): pass
 eligible=[]
 for f in sorted(FEATURES-ALREADY_AUDITED):
  vals=[blocks[k].get(f) for k in sorted(blocks) if f in blocks[k]]
  if len(vals)!=3 or any(a.get('n',0)<3 or b.get('n',0)<3 for a,b in vals): continue
  if all(a.get('total_return',0)>b.get('total_return',0) and (a.get('profit_factor') or 0)>(b.get('profit_factor') or 0) for a,b in vals): eligible.append(f)
 print('DISCOVERY_STATUS',{'mode':'strict_fixed_diagnostics','oos_touched':False})
 print('DISCOVERY_RESULT',{'eligible_candidates':eligible,'already_audited':sorted(ALREADY_AUDITED)})
 if not eligible: print('DECISION NO_VALIDATED_NEXT_HYPOTHESIS'); return 0
 feature=eligible[0]; c={'feature':feature,'single_change':feature,'selection_data':'IS+VALIDATION_ONLY','oos_touched':False}; PENDING.write_text(json.dumps(c,indent=2))
 q=json.loads(QUEUE.read_text()); q.setdefault('candidates',[]); name='BC6_'+feature
 if not any(x.get('name')==name for x in q['candidates']): q['candidates'].append({'name':name,'audit_script':'audit_candidate_feature.py'}); QUEUE.write_text(json.dumps(q,indent=2))
 print('REGISTERED_CANDIDATE',c); print('DECISION REGISTERED_NEXT_CANDIDATE',name); return 0
if __name__=='__main__': raise SystemExit(main())
