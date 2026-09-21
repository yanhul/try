#!/usr/bin/env python3
"""Bounded external-research escalation for failed autonomous repair."""
from __future__ import annotations
import base64, hashlib, json, os, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/"research"/"repair_research"; HISTORY=DIR/"history"; LATEST=DIR/"latest.json"; STATE=DIR/"state.json"
MAX_RESULTS=5; MAX_README=12000; MAX_ATTEMPTS=3
STOPWORDS={"error","failed","failure","traceback","test","tests","assert","expected","actual","python","github","workflow","repair","provider","hold","exception"}
def sha256_bytes(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def canonical(value)->str:return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"))
def failure_signature(failure:dict)->str:
    raw=canonical({"error":failure.get("error") or failure.get("reason") or "","step":failure.get("step") or "","log":str(failure.get("ci_failure_log_tail") or "")[-4000:]})
    return sha256_bytes(raw.encode())
def query_from_failure(failure:dict)->str:
    text=" ".join([str(failure.get("error") or ""),str(failure.get("reason") or ""),str(failure.get("step") or ""),str(failure.get("ci_failure_log_tail") or "")[-3000:]])
    tokens=re.findall(r"[A-Za-z][A-Za-z0-9_.:-]{2,}",text.lower()); chosen=[]
    for token in tokens:
        token=token.strip("._:-")
        if token in STOPWORDS or token in chosen or token.startswith(("http","sha256")): continue
        chosen.append(token)
        if len(chosen)>=8: break
    return " ".join(chosen) or "autonomous agent repair durable workflow"
def api(path:str):
    headers={"Accept":"application/vnd.github+json","User-Agent":"try-repair-research/2"}; token=os.getenv("GITHUB_TOKEN")
    if token: headers["Authorization"]="Bearer "+token
    with urllib.request.urlopen(urllib.request.Request("https://api.github.com"+path,headers=headers),timeout=15) as r:return json.loads(r.read().decode("utf-8",errors="replace"))
def search_repositories(query:str):
    data=api("/search/repositories?"+urllib.parse.urlencode({"q":query,"per_page":MAX_RESULTS}))
    return data.get("items",[])[:MAX_RESULTS]
def repository_head_sha(full_name:str,ref:str|None):
    if not ref:return None
    try:
        data=api("/repos/"+full_name+"/commits/"+urllib.parse.quote(ref,safe="")); sha=data.get("sha")
        return sha if isinstance(sha,str) and len(sha)==40 else None
    except Exception:return None
def readme(full_name:str,ref:str|None):
    path="/repos/"+full_name+"/contents/README.md"
    if ref:path+="?"+urllib.parse.urlencode({"ref":ref})
    try:
        data=api(path)
        if data.get("encoding")!="base64" or not data.get("content"):return None
        return base64.b64decode(data["content"])[:MAX_README].decode("utf-8",errors="replace")
    except Exception:return None
def _load_state():
    if not STATE.exists():return {"attempts":[]}
    try:
        value=json.loads(STATE.read_text(encoding="utf-8")); return value if isinstance(value,dict) else {"attempts":[]}
    except Exception:return {"attempts":[]}
def run(failure:dict)->dict:
    sig=failure_signature(failure); query=query_from_failure(failure); qdigest=sha256_bytes(query.encode()); state=_load_state()
    prior=[x for x in state.get("attempts",[]) if isinstance(x,dict)]; key=(sig,qdigest)
    if sum(1 for x in prior if (x.get("failure_signature"),x.get("query_digest"))==key)>=MAX_ATTEMPTS:
        return {"status":"HOLD","reason":"research_budget_exhausted","failure_signature":sig,"query":query,"query_digest":qdigest}
    attempt=len([x for x in prior if x.get("failure_signature")==sig])+1; run_id=str(os.getenv("GITHUB_RUN_ID") or "local"); sources=[]
    try: repos=search_repositories(query)
    except Exception as exc:
        return {"status":"HOLD","reason":f"research_search_failed:{type(exc).__name__}","failure_signature":sig,"query":query,"query_digest":qdigest}
    for repo in repos:
        full=repo.get("full_name")
        if not full:continue
        ref=repo.get("default_branch"); head_sha=repository_head_sha(full,ref); text=readme(full,ref)
        source={"source_type":"github_repository","source_url":repo.get("html_url"),"repository":full,"source_ref":ref,"source_sha":head_sha,"title":repo.get("name"),"description":repo.get("description"),"stars":repo.get("stargazers_count"),"readme_excerpt":text}
        source["source_digest"]=sha256_bytes(canonical(source).encode()); sources.append(source)
    attempt_id=f"{sig[:16]}-{attempt}-{run_id}"
    evidence={"schema_version":2,"research_attempt_id":attempt_id,"failure_signature":sig,"query":query,"query_digest":qdigest,"attempt":attempt,"created_at":datetime.now(timezone.utc).isoformat(),"source_selection":"github_api_relevance_order; stars_metadata_only","sources":sources,"research_only":True,"mutation_authority":"AIOS","candidate_status":"UNTRUSTED_EVIDENCE"}
    evidence["evidence_digest"]=sha256_bytes(canonical(evidence).encode())
    DIR.mkdir(parents=True,exist_ok=True); HISTORY.mkdir(parents=True,exist_ok=True); history_path=HISTORY/f"{attempt_id}.json"
    if history_path.exists():
        existing=json.loads(history_path.read_text(encoding="utf-8"))
        if existing.get("evidence_digest")!=evidence["evidence_digest"]:raise RuntimeError("immutable_history_collision")
    else: history_path.write_text(json.dumps(evidence,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    LATEST.write_text(json.dumps(evidence,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    prior.append({"research_attempt_id":attempt_id,"failure_signature":sig,"query_digest":qdigest,"evidence_digest":evidence["evidence_digest"]})
    STATE.write_text(json.dumps({"schema_version":2,"attempts":prior[-100:]},indent=2,sort_keys=True)+"\n",encoding="utf-8")
    evidence["status"]="EVIDENCE_COLLECTED" if sources else "NO_EVIDENCE"; return evidence
if __name__=="__main__":
    result=run(json.loads(os.environ.get("REPAIR_FAILURE_JSON","{}"))); print(json.dumps(result,ensure_ascii=False,sort_keys=True)); raise SystemExit(0 if result.get("status") in {"EVIDENCE_COLLECTED","NO_EVIDENCE"} else 2)
