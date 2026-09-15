"""Adaptive research-frontier scheduling.

Ranks research opportunities only. It derives one terminal outcome per
candidate from the append-only lifecycle so retries/replays cannot inflate
family statistics. No promotion authority lives here.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, math
from pathlib import Path
from typing import Any, Iterable, Mapping

TERMINAL=frozenset({"PROMOTED","REJECTED","EXHAUSTED"})

@dataclass(frozen=True)
class FamilyStats:
    family:str; trials:int; successes:int; failures:int; priority:float

def _stable(value:str)->int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12],16)

def _candidate_families(root:Path)->dict[str,str]:
    out={}; directory=root/"research"/"autonomous_candidates"
    if not directory.exists(): return out
    for path in sorted(directory.glob("BC*.json")):
        try:
            data=json.loads(path.read_text(encoding="utf-8")); cid=str(data.get("candidate_hash") or data.get("candidate_id") or "")
            spec=data.get("discovery_spec") or {}; family=str(spec.get("mechanism_family") or data.get("mechanism_family") or "")
            if cid and family: out[cid]=family
        except (OSError,ValueError,TypeError): continue
    return out

def _terminal_outcomes(root:Path)->dict[str,str]:
    """Return exactly one terminal outcome per candidate: the last one seen."""
    path=root/"research"/"research_lifecycle.jsonl"; latest={}
    if not path.exists(): return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try:
            event=json.loads(line); cid=str(event.get("candidate_id") or ""); state=str(event.get("to_state") or "")
            if cid and state in TERMINAL: latest[cid]=state
        except (OSError,ValueError,TypeError): continue
    return latest

def rank_families(families:Iterable[str],root:Path)->list[FamilyStats]:
    """Rank exploration with smoothed UCB; scheduling only, never promotion."""
    families=sorted({str(f) for f in families if str(f)}); mapping=_candidate_families(root); outcomes=_terminal_outcomes(root)
    total_trials=sum(1 for cid in mapping if cid in outcomes); stats=[]
    for family in families:
        successes=sum(1 for cid,fam in mapping.items() if fam==family and outcomes.get(cid)=="PROMOTED")
        failures=sum(1 for cid,fam in mapping.items() if fam==family and outcomes.get(cid) in {"REJECTED","EXHAUSTED"})
        trials=successes+failures
        if trials==0: priority=float("inf")
        else:
            mean=(successes+1.0)/(trials+2.0)
            bonus=math.sqrt(2.0*math.log(max(2,total_trials)+1.0)/trials)
            priority=mean+bonus
        stats.append(FamilyStats(family,trials,successes,failures,priority))
    return sorted(stats,key=lambda x:(-x.priority,_stable(x.family)))

def select_survivor(survivors:Iterable[Mapping[str,Any]],root:Path)->tuple[Mapping[str,Any],FamilyStats]:
    items=[s for s in survivors if isinstance(s,Mapping)]
    if not items: raise ValueError("empty_survivor_frontier")
    ranked=rank_families([str(s.get("family") or "") for s in items],root); top=ranked[0]
    candidates=[s for s in items if str(s.get("family") or "")==top.family]
    candidates.sort(key=lambda s:_stable(str(s.get("candidate_id") or s.get("source_url") or "")))
    return candidates[0],top

__all__=["FamilyStats","rank_families","select_survivor"]
