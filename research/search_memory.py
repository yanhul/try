from __future__ import annotations
import json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'research'/'search_memory.json'

def load():
    if not STATE.exists(): return {'schema_version':1,'families':{},'structural':{},'recent':[],'stagnation':{'no_new':0,'failures':0}}
    try:
        x=json.loads(STATE.read_text(encoding='utf-8')); return x if isinstance(x,dict) else {}
    except Exception: return {}

def record(candidate:dict,outcome:str,metrics:dict|None=None):
    s=load(); s.setdefault('families',{}); s.setdefault('structural',{}); s.setdefault('recent',[]); s.setdefault('stagnation',{'no_new':0,'failures':0})
    spec=candidate.get('discovery_spec') or {}; family=str(spec.get('mechanism_family') or candidate.get('mechanism_family') or 'unknown')
    key='|'.join('' if spec.get(k) is None else str(spec.get(k)) for k in ('mechanism_family','operator','left','right','direction'))
    b=s['families'].setdefault(family,{'tested':0,'pass':0,'fail':0,'score':0.0}); b['tested']+=1
    if outcome in {'PASS','PROMOTE','OOS_PASS'}: b['pass']+=1
    if outcome in {'FAIL','REJECT','OOS_FAIL'}: b['fail']+=1
    m=metrics or {}
    try: score=max(0.0,float(m.get('profit_factor',0))-1.0)+max(0.0,float(m.get('total_return',0)))
    except (TypeError,ValueError): score=0.0
    n=b['tested']; b['score']=((b['score']*(n-1))+score)/n
    q=s['structural'].setdefault(key,{'tested':0,'pass':0,'fail':0}); q['tested']+=1
    if outcome in {'PASS','PROMOTE','OOS_PASS'}: q['pass']+=1
    if outcome in {'FAIL','REJECT','OOS_FAIL'}: q['fail']+=1
    s['recent']=(s['recent']+[{'bc':candidate.get('bc'),'key':key,'family':family,'outcome':outcome}])[-100:]
    if outcome in {'FAIL','REJECT','OOS_FAIL'}: s['stagnation']['failures']=int(s['stagnation'].get('failures',0))+1
    s['stagnation']['no_new']=0
    STATE.parent.mkdir(parents=True,exist_ok=True); STATE.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n',encoding='utf-8'); return s

def rank_families(families, seed=0):
    s=load(); rows=[]
    for i,f in enumerate(families):
        x=s.get('families',{}).get(f,{}); n=int(x.get('tested',0)); fail=int(x.get('fail',0)); score=float(x.get('score',0.0))
        priority=10.0 if not n else score + 1.5/math.sqrt(n) - 0.75*fail/n
        # Stable deterministic tie-break; seed prevents every campaign epoch having the same tie order.
        tie=((int(seed)*1103515245 + i*12345) & 0x7fffffff)
        rows.append((priority,tie,f))
    return [f for _,_,f in sorted(rows,reverse=True)]

def rank(families): return rank_families(families)

def note_no_new():
    s=load(); s.setdefault('stagnation',{'no_new':0,'failures':0}); s['stagnation']['no_new']=int(s['stagnation'].get('no_new',0))+1
    STATE.parent.mkdir(parents=True,exist_ok=True); STATE.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n',encoding='utf-8'); return s['stagnation']['no_new']
