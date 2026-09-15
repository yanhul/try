"""Durable, fail-closed search memory for autonomous research.

This module stores only evidence already produced by the immutable evaluator.
It ranks *where to search next*; it never changes evaluation results or OOS
selection. Search memory is intentionally append/rebuild friendly and atomic.
"""
from __future__ import annotations
import hashlib,json,math,os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MEMORY_PATH=ROOT/"research"/"search_memory.json"


def _finite(x):
    try:
        x=float(x)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None


def structural_key(candidate):
    spec=candidate.get("discovery_spec") or {}
    return "|".join("" if spec.get(k) is None else str(spec.get(k)) for k in
                     ("mechanism_family","operator","left","right","direction"))


def _score(result):
    m=result.get("metrics") or result.get("VALIDATION",{}).get("metrics",{})
    pf=_finite(m.get("profit_factor")); ret=_finite(m.get("total_return")); dd=_finite(m.get("max_drawdown"))
    trades=_finite(m.get("trades")) or _finite(m.get("trade_count")) or 0.0
    # Ranking is deliberately bounded and only used for search ordering.
    pf=max(0.0,min(3.0,pf if pf is not None else 0.0))
    ret=max(-1.0,min(2.0,ret if ret is not None else -1.0))
    dd=max(0.0,min(1.0,abs(dd) if dd is not None else 1.0))
    activity=min(1.0,trades/50.0)
    return round(0.45*(pf/3.0)+0.30*((ret+1.0)/3.0)+0.15*(1.0-dd)+0.10*activity,8)


def load():
    if not MEMORY_PATH.exists(): return {"schema_version":1,"candidates":{},"families":{},"failures":0}
    try:
        x=json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        if not isinstance(x,dict) or x.get("schema_version")!=1: raise ValueError("invalid_search_memory")
        return x
    except Exception as e: raise RuntimeError(f"search_memory_corrupt:{e}")


def record(candidate,result,decision):
    data=load(); key=structural_key(candidate); family=(candidate.get("discovery_spec") or {}).get("mechanism_family") or "discovered_primitive"
    entry={"bc":candidate.get("bc"),"parent_bc":candidate.get("parent_bc"),"candidate_hash":candidate.get("candidate_hash"),"decision":decision,"score":_score(result),"hypothesis_id":candidate.get("hypothesis_id")}
    data["candidates"][key]=entry
    f=data["families"].setdefault(family,{"tested":0,"pass":0,"fail":0,"score_sum":0.0})
    f["tested"]+=1; f["pass"]+=decision in {"PASS","PROMOTE","OOS_PASS"}; f["fail"]+=decision in {"FAIL","REJECT","OOS_FAIL"}; f["score_sum"]+=entry["score"]
    data["failures"]=int(data.get("failures",0))+(decision in {"FAIL","REJECT","OOS_FAIL"})
    tmp=MEMORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(tmp,MEMORY_PATH)
    return entry


def rank_families(families,seed):
    data=load(); ranked=[]
    for i,f in enumerate(families):
        x=data["families"].get(f,{"tested":0,"pass":0,"fail":0,"score_sum":0.0})
        n=x["tested"]; mean=x["score_sum"]/n if n else 0.5
        # UCB-like bounded exploration bonus; seed breaks deterministic ties only.
        total=max(1,sum(v.get("tested",0) for v in data["families"].values()))
        bonus=0.45*math.sqrt(math.log(total+2)/(n+1))
        ranked.append((mean+bonus+((seed+i)%997)*1e-9,f))
    return [f for _,f in sorted(ranked,reverse=True)]


def stagnant(data=None,window=8):
    data=data or load(); entries=list(data.get("candidates",{}).values())
    if len(entries)<window:return False
    recent=entries[-window:]
    return all(x.get("decision") in {"FAIL","REJECT","OOS_FAIL"} for x in recent)
