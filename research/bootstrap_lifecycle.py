#!/usr/bin/env python3
"""Bootstrap only BC1 on a clean lifecycle; never resurrect later state."""
from __future__ import annotations
import json
from pathlib import Path
from autonomous_hypothesis import load_candidate, write_candidate
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'research'/'autonomous_candidates'/'BC1.json'; QUEUE=ROOT/'research'/'bc_queue.json'; STATE=ROOT/'research'/'bc_lifecycle_state.json'; FAILURE=ROOT/'research'/'failure_analysis'/'BC1.json'
state=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
next_bc=int(state.get('next_bc',2)); last_bc=int(state.get('last_bc',1))
if next_bc!=2 or last_bc!=1:
 print(f'BOOTSTRAP_PRESERVE_LIFECYCLE next_bc={next_bc} last_bc={last_bc}'); raise SystemExit(0)
candidate=load_candidate(SRC,1,0); write_candidate(SRC,candidate)
queue=json.loads(QUEUE.read_text(encoding='utf-8')) if QUEUE.exists() else []
if not isinstance(queue,list): raise SystemExit('bc_queue.json must be a list')
queue=[x for x in queue if isinstance(x,dict) and int(x.get('bc',-1))==1]
if not any(x.get('candidate_hash')==candidate['candidate_hash'] for x in queue): queue.append(candidate)
QUEUE.write_text(json.dumps(queue,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(f'BOOTSTRAP_REGISTERED BC1 hash={candidate["candidate_hash"]} failure_analysis={FAILURE}')
