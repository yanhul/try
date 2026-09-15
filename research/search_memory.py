"""Durable adaptive search memory for autonomous research.

Only completed evaluator/OOS artifacts may affect search ordering. Search memory
never changes a verdict, OOS selection, authority, or candidate contents.
"""
from __future__ import annotations
import json,math,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; MEMORY_PATH=ROOT/"research"/"search_memory.json"
def _finite(x):
 try:
  x=float(x);return x if math.isfinite(x) else None
 except (TypeError,ValueError):return None
def structural_key(candidate):
 spec=candidate.get("discovery_spec") or {}
 return "|".join("" if spec.get(k) is None else str(spec.get(k)) for k in ("mechanism_family","operator","left","right","direction"))
def _family(candidate):return (candidate.get("discovery_spec") or {}).get("mechanism_family") or "discovered_primitive"
def _score(result):
 m=result.get("metrics") or result.get("VALIDATION",{}).get("metrics",{});pf=_finite(m.get("profit_factor"));ret=_finite(m.get("total_return"));dd=_finite(m.get("max_drawdown"));tr=_finite(m.get("trades")) or _finite(m.get("trade_count")) or 0.0
 pf=max(0,min(3,pf if pf is not None else 0));ret=max(-1,min(2,ret if ret is not None else -1));dd=max(0,min(1,abs(dd) if dd is not None else 1));activity=min(1,tr/50)
 return round(.45*pf/3+.30*(ret+1)/3+.15*(1-dd)+.10*activity,8)
def load():
 if not MEMORY_PATH.exists():return {"schema_version":1,"candidates":{},"families":{},"failures":0}
 try:
  x=json.loads(MEMORY_PATH.read_text(encoding="utf-8"));
  if not isinstance(x,dict) or x.get("schema_version")!=1:raise ValueError("invalid_search_memory")
  return x
 except Exception as e:raise RuntimeError(f"search_memory_corrupt:{e}")
def record(candidate,result,decision):
 data=load();key=structural_key(candidate);family=_family(candidate);old=data["candidates"].get(key)
 if old and old.get("candidate_hash")==candidate.get("candidate_hash"):return old
 entry={"bc":candidate.get("bc"),"parent_bc":candidate.get("parent_bc"),"candidate_hash":candidate.get("candidate_hash"),"decision":decision,"score":_score(result),"hypothesis_id":candidate.get("hypothesis_id")};data["candidates"][key]=entry
 f=data["families"].setdefault(family,{"tested":0,"pass":0,"fail":0,"score_sum":0.0});f["tested"]+=1;f["pass"]+=decision in {"PASS","PROMOTE","OOS_PASS"};f["fail"]+=decision in {"FAIL","REJECT","OOS_FAIL"};f["score_sum"]+=entry["score"]
 data["failures"]=int(data.get("failures",0))+(decision in {"FAIL","REJECT","OOS_FAIL"});tmp=MEMORY_PATH.with_suffix(".tmp");tmp.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n",encoding="utf-8");os.replace(tmp,MEMORY_PATH);return entry
def rebuild_from_artifacts(data=None):
 """Reconcile memory from durable artifacts after interrupted/non-memory-aware runs."""
 data=data or load();canddir=ROOT/"research"/"autonomous_candidates";faildir=ROOT/"research"/"failure_analysis";oosdir=ROOT/"research"/"oos"
 if not canddir.exists():return data
 for p in sorted(canddir.glob("BC*.json")):
  try:c=json.loads(p.read_text(encoding="utf-8"));bc=int(c["bc"]);key=structural_key(c);decision=None;result={}
  except Exception:continue
  fp=faildir/f"BC{bc}.json"
  if fp.exists():
   try:
    f=json.loads(fp.read_text(encoding="utf-8"));decision="OOS_FAIL" if f.get("oos_verdict")=="OOS_FAIL" else "REJECT"
   except Exception:continue
  op=oosdir/f"BC{bc}_oos_result.json"
  if op.exists():
   try:
    o=json.loads(op.read_text(encoding="utf-8"));decision="OOS_PASS" if o.get("oos_passed") is True else ("OOS_FAIL" if o.get("oos_executed") is True else decision);result=o
   except Exception:continue
  vp=ROOT/"research"/f"bc{bc}_validation_result.json"
  if vp.exists() and decision is None:
   try:
    v=json.loads(vp.read_text(encoding="utf-8"));decision="VALIDATION_PASS" if v.get("validation_passed") is True else "VALIDATION_FAIL";result=v
   except Exception:continue
  if decision and (not data["candidates"].get(key) or data["candidates"][key].get("candidate_hash")!=c.get("candidate_hash")):
   f=data["families"].setdefault(_family(c),{"tested":0,"pass":0,"fail":0,"score_sum":0.0});entry={"bc":bc,"parent_bc":c.get("parent_bc"),"candidate_hash":c.get("candidate_hash"),"decision":decision,"score":_score(result),"hypothesis_id":c.get("hypothesis_id")};data["candidates"][key]=entry
 # rebuild aggregate counts exactly from candidate entries
 fam={}
 for e in data["candidates"].values():
  family=e.get("family") or ""
  if not family:
   continue
  z=fam.setdefault(family,{"tested":0,"pass":0,"fail":0,"score_sum":0.0});z["tested"]+=1;z["pass"]+=e.get("decision") in {"PASS","PROMOTE","OOS_PASS"};z["fail"]+=e.get("decision") in {"FAIL","REJECT","OOS_FAIL"};z["score_sum"]+=float(e.get("score",0))
 if fam:data["families"].update(fam)
 return data
def rank_families(families,seed):
 data=rebuild_from_artifacts();ranked=[];total=max(1,sum(v.get("tested",0) for v in data["families"].values()))
 for i,f in enumerate(families):
  x=data["families"].get(f,{"tested":0,"pass":0,"fail":0,"score_sum":0});n=x["tested"];mean=x["score_sum"]/n if n else .5;bonus=.45*math.sqrt(math.log(total+2)/(n+1));ranked.append((mean+bonus+((seed+i)%997)*1e-9,f))
 return [f for _,f in sorted(ranked,reverse=True)]
def stagnant(data=None,window=8):
 data=data or load();entries=list(data.get("candidates",{}).values());
 if len(entries)<window:return False
 return all(x.get("decision") in {"FAIL","REJECT","OOS_FAIL","VALIDATION_FAIL"} for x in entries[-window:])
