#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, tempfile
from pathlib import Path
from research.repair_research import run as research_run
from research.aios_repair_provider import propose as direct_propose

MAX_FILES=40
MAX_BYTES=42000

def git(*args):
    return subprocess.run(["git",*args],text=True,capture_output=True,check=True).stdout.strip()

def snapshot(log):
    names=git("ls-tree","-r","--name-only","HEAD").splitlines()
    paths=[p for p in names if p.endswith(".py") and not p.startswith("tests/") and not p.startswith(".github/")]
    mentioned={line.strip() for line in log.splitlines() if "/" in line.strip()}
    paths.sort(key=lambda p:(0 if any(p in m for m in mentioned) else 1,p))
    out={}; used=0
    for p in paths:
        if len(out)>=MAX_FILES or used>=MAX_BYTES: break
        try: data=Path(p).read_text(encoding="utf-8",errors="replace")
        except OSError: continue
        data=data[:min(8000,MAX_BYTES-used)]
        if data: out[p]=data; used+=len(data.encode())
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
    contract={"contract_type":CONTRACT_TYPE,"task_id":f"try-ci-repair-{run_id}","scope":"repository","actor":"try-autonomous-repair",
              "capabilities":["repo_patch@1"],"input_digest":"sha256:ci-failure","allowed_effects":["external_effect"],
              "evidence_required":["OBSERVED"],"max_attempts":3,"terminal_states":["OBSERVED_SUCCESS","OBSERVED_FAILURE"],"policy_digest":pd}
    stored=persist_contract(root,contract)
    permit=persist_permit(root,stored,issuer="try-ci-repair-authority")
    return stored["contract_id"],permit["permit_id"]

def main():
    base=os.environ["REPAIR_BASE_SHA"]; run_id=int(os.environ["REPAIR_RUN_ID"])
    log=Path(os.environ["REPAIR_LOG"]).read_text(encoding="utf-8",errors="replace")[-80000:]
    failure={"run_id":run_id,"sha":base,"attempt":1,"ci_failure_log_tail":log}
    from core.agent_repair_worker import AgentRepairWorker,ProposedFile
    proposals=[]
    with tempfile.TemporaryDirectory(prefix="try-aios-authority-") as td:
        aios=Path(td)/"aios"; aios.mkdir()
        cid,pid=authority(aios,run_id)
        worker=AgentRepairWorker(Path("."),object(),allowed_test_commands=(("python","-m","pytest","-q"),),
                                 timeout_seconds=900,aios_dir=aios,contract_id=cid,permit_id=pid,actor="try-autonomous-repair")
        for attempt in range(1,4):
            failure["attempt"]=attempt
            evidence=research_run(failure)
            failure["repair_research_evidence"]=evidence
            if evidence.get("status") not in {"EVIDENCE_COLLECTED","NO_EVIDENCE"}: break
            try:
                proposal=direct_propose({"request_id":f"try-ci-repair:{run_id}:{attempt}","repository":"yanhul/try",
                    "sha":base,"attempt":attempt,"failure":failure,"source_snapshot":snapshot(log)})
            except Exception as exc:
                proposal={"status":"HOLD","reason":f"{type(exc).__name__}:{exc}"}
            Path(f"repair-proposal-{attempt}.json").write_text(json.dumps(proposal,indent=2,sort_keys=True),encoding="utf-8")
            if proposal.get("status")=="HOLD": break
            files=tuple(ProposedFile(x["path"],x["content"]) for x in proposal["files"])
            applied=worker.apply_via_aios(base_sha=base,files=files,logical_operation_id=f"try-ci-repair:{run_id}:attempt:{attempt}",
                                          allowed_dirty_paths=worker._owned_dirty_paths.copy() if worker._owned_dirty_paths else frozenset())
            tested=worker.test()
            result={"attempt":attempt,"proposal":proposal,"apply":dict(applied),
                    "test":{"status":tested.status,"evidence_refs":list(tested.evidence_refs),"details":dict(tested.details)},
                    "research_attempt_id":evidence.get("research_attempt_id"),"research_evidence_digest":evidence.get("evidence_digest")}
            proposals.append(result)
            Path(f"repair-result-{attempt}.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
            if tested.status=="PASS":
                Path("repair-result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
                print(json.dumps({"status":"PASS","attempt":attempt}))
                return 0
            failure["previous_repair_result"]=result
            details=tested.details.get("results",[]) if tested.details else []
            failure["ci_failure_log_tail"]=(details[-1].get("stderr_tail","") if details else "")[-80000:]
            log=failure["ci_failure_log_tail"]
    Path("repair-result.json").write_text(json.dumps({"status":"FAIL","attempts":proposals},indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps({"status":"FAIL","attempts":len(proposals)}))
    return 2

if __name__=="__main__":
    raise SystemExit(main())
