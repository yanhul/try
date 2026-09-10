#!/usr/bin/env python3
"""Compile discovered ideas into executable, auditable feature candidates.

The compiler is deliberately constrained: discovery can choose only registered
primitive operators and existing causal feature columns. It cannot change the
campaign policy, OOS gate, or execution assumptions.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/'research'/'discovery'/'primitive_registry.json'
OUT=ROOT/'research'/'discovery'/'compiled_candidates.json'
DEFAULT={
 'operators': ['identity','ratio','difference','zscore','rolling_mean','rolling_std','lag','delta','rank'],
 'columns': ['open','high','low','close','volume','volume_ratio','range_ratio','close_location','vwap_distance'],
 'windows': [3,5,10,20,50,100],
}
def load():
 if not REGISTRY.exists(): return DEFAULT
 x=json.loads(REGISTRY.read_text(encoding='utf-8'))
 return {**DEFAULT,**x}
def valid_name(x): return isinstance(x,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',x) is not None
def main():
 r=load(); ops=set(r['operators']); cols=set(r['columns']); wins=set(map(int,r['windows']))
 candidates=[]
 for col in sorted(cols):
  candidates.append({'operator':'identity','column':col})
  for op in ('zscore','rolling_mean','rolling_std','delta','rank'):
   if op in ops:
    for w in sorted(wins): candidates.append({'operator':op,'column':col,'window':w})
 for a in sorted(cols):
  for b in sorted(cols):
   if a>=b: continue
   for op in ('ratio','difference'):
    if op in ops: candidates.append({'operator':op,'left':a,'right':b})
 for c in candidates:
  assert valid_name(c.get('column',c.get('left','x')))
  c['candidate_id']='DISC-'+hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:16]
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps({'schema_version':1,'source':'constrained_registry','candidates':candidates},indent=2)+'\n',encoding='utf-8')
 print(f'COMPILED_DISCOVERY candidates={len(candidates)} output={OUT}')
if __name__=='__main__': main()
