#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, tempfile
from pathlib import Path
from research.repair_research import run as research_run

MAX_ATTEMPTS=3
MAX_SOURCE_FILES=80
MAX_SOURCE_BYTES=90000

def git(*args):
    return subprocess.run(["git", *args], cwd=".", text=True, capture_output=True, check=True).stdout.strip()

def source_snapshot(sha, log):
    paths=git("ls-tree","-r","--name-only",sha).splitlines()
    mentioned={line.strip().split()[0].rstrip(":") for line in log.splitlines() if "/" in line}
    paths=[p for p in paths if p.endswith(".py") and not p.startswith(("tests/","\.github/","\.aios/","secrets/"))]
    paths.sort(key=lambda p:(0 if any(p in x for x in mentioned) else 1,p))
    out={}; used=0
    for p in paths:
        if len(out)>=MAX_SOURCE_FILES or used>=MAX_SOURCE_BYTES: break
        raw=subprocess.run(["git","show",f"{sha}:{p}"],capture_output=True,text=True,check=False).stdout
        if not raw: continue
        raw=raw[:10000]
        out[p]=raw
        used+=len(raw.encode())
    return out

def authority(root, run_id):
    from core.authority import persist_contract,persist_permit
    from core.capabilities import Capability,CapabilityRegistry
    from core.contract import CONTRACT_TYPE
    from core.policy_registry import persist_policy
    reg=CapabilityRegistry()
    reg.register(Capability("repo_patch","1","AIOS","external_effect",inputs=("patch",),outputs=("observation",),status="ACTIVE"))
    reg.persist(root,actor="try-autonomous-repair")
    pd=persist_policy(root,{"policy_type":"GOVERNING_POLICY","task":"try-ci-repair","allowed_effects":["external_effect"]})
    contract={"contract_type":CONTRACT_TYPE,"task_id":f"try-ci-repair-{run_id}","scope":"repository",
              "actor":"try-autonomous-repair","capabilities":["repo_patch@1"],"input_digest":"sha256:ci-failure",
              "allowed_effects":["external_effect"],"evidence_required":["OBSERVED"],"max_attempts":3,
              "terminal_states":["OBSERVED_SUCCESS","OBSERVED_FAILURE"],"policy_digest":pd}
    stored=persist_contract(root,contract)
    permit=persist_permit(root,stored,issuer="try-ci-repair-authority")
    return stored["contract_id"],permit["permit_id"]

def main():
    base=os.environ["AIOS_REPAIR_SHA"]; run_id=int(os.environ["AIOS_REPAIR_RUN_ID"])
    log_path=Path(os.environ["AIOS_REPAIR_LOG"])
    log=log_path.read_text(encoding="utf-8",errors="replace")[-80000:]
    evidence={}
    evidence_path=os.environ.get("AIOS_REPAIR_EVIDENCE","")
    if evidence_path and Path(evidence_path).exists():
        try: evidence=json.loads(Path(evidence_path).read_text(encoding="utf-8"))
        except Exception: evidence={}
    failure={"run_id":run_id,"sha":base,"attempt":1,"ci_failure_log_tail":log,"repair_research_evidence":evidence}
    from core.agent_repair_worker import AgentRepairWorker,ProposedFile
    from core.try_repair_provider import propose,TryRepairProviderError
    results=[]
    with tempfile.TemporaryDirectory(prefix="try-aios-authority-") as td:
        aios=Path(td)/"aios"; aios.mkdir()
        cid,pid=authority(aios,run_id)
        worker=AgentRepairWorker(Path("."),object(),allowed_test_commands=(("python","-m","pytest","-q"),),
                                 timeout_seconds=900,aios_dir=aios,contract_id=cid,permit_id=pid,actor="try-autonomous-repair")
        owned=frozenset()
        for attempt in range(1,MAX_ATTEMPTS+1):
            failure["attempt"]=attempt
            if attempt > 1:
                evidence=research_run(failure)
                failure["repair_research_evidence"]=evidence
                if evidence.get("status") not in {"EVIDENCE_COLLECTED","NO_EVIDENCE"}:
                    results.append({"attempt":attempt,"status":"HOLD","reason":evidence.get("reason","research_hold")})
                    break
            req_id=f"try-ci-repair:{run_id}:{attempt}"
            try:
                proposal=propose(request_id=req_id,repository="yanhul/try",sha=base,attempt=attempt,
                                  failure=failure,source=source_snapshot(base,log))
            except TryRepairProviderError as exc:
                proposal={"status":"HOLD","reason":str(exc)}
            Path(f"repair-proposal-{attempt}.json").write_text(json.dumps(proposal,indent=2,sort_keys=True),encoding="utf-8")
            if proposal.get("status")=="HOLD":
                results.append({"attempt":attempt,"status":"HOLD","reason":proposal.get("reason")})
                break
            files=tuple(ProposedFile(x["path"],x["content"]) for x in proposal["files"])
            applied=worker.apply_via_aios(base_sha=base,files=files,
                logical_operation_id=req_id,allowed_dirty_paths=owned)
            owned=frozenset(set(owned)|{x.path for x in files})
            tested=worker.test()
            result={"attempt":attempt,"status":tested.status,"proposal":proposal,"apply":dict(applied),
                    "test":{"status":tested.status,"evidence_refs":list(tested.evidence_refs),"details":dict(tested.details)},
                    "research_evidence_digest":evidence.get("evidence_digest")}
            results.append(result)
            Path(f"repair-result-{attempt}.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
            if tested.status=="PASS":
                Path("repair-result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
                print(json.dumps({"status":"PASS","attempt":attempt}))
                return 0
            details=tested.details.get("results",[]) if tested.details else []
            log=(details[-1].get("stderr_tail","") if details else "")[-80000:]
            failure["ci_failure_log_tail"]=log
            failure["previous_repair_result"]=result
    Path("repair-result.json").write_text(json.dumps({"status":"FAIL","attempts":results},indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps({"status":"FAIL","attempts":len(results)}))
    return 2

if __name__=="__main__":
    raise SystemExit(main())
