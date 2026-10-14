#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, subprocess, tempfile
from pathlib import Path
from research.repair_research import run as research_run
from research.repair_checkpoint import get_checkpoint, persist_checkpoint, RepairCheckpointError

MAX_ATTEMPTS=3
MAX_SOURCE_FILES=80
MAX_SOURCE_BYTES=90000

def select_resume_attempt(prior, *, repository, sha, max_attempts=MAX_ATTEMPTS):
    """Resume only after a persisted BLOCKED checkpoint with matching identity."""
    if prior is None:
        return 1
    if prior.get("repository") != repository or prior.get("sha") != sha.lower():
        raise RepairCheckpointError("checkpoint_identity_conflict_for_resume")
    if prior.get("state") != "BLOCKED":
        raise RepairCheckpointError(
            f"checkpoint_not_resumable:{prior.get('state')}:{prior.get('phase')}"
        )
    previous_attempt = prior.get("attempt")
    if isinstance(previous_attempt, bool) or not isinstance(previous_attempt, int) or previous_attempt < 1:
        raise RepairCheckpointError("checkpoint_attempt_invalid_for_resume")
    next_attempt = previous_attempt + 1
    if next_attempt > max_attempts:
        raise RepairCheckpointError("checkpoint_attempt_budget_exhausted")
    return next_attempt


def is_interrupted_working_checkpoint(prior, *, repository, sha):
    """Identify only a structurally valid, identity-matched WORKING record."""
    return (
        isinstance(prior, dict)
        and prior.get("state") == "WORKING"
        and prior.get("repository") == repository
        and prior.get("sha") == sha.lower()
        and isinstance(prior.get("attempt"), int)
        and not isinstance(prior.get("attempt"), bool)
        and prior.get("attempt") >= 1
        and prior.get("phase") in {"OBSERVE", "DECIDE", "PROPOSE", "VERIFY", "PERSIST", "RESUME"}
    )


def git(*args):
    return subprocess.run(["git", *args], cwd=".", text=True, capture_output=True, check=True).stdout.strip()

def source_snapshot(sha, log, owned=frozenset()):
    paths=git("ls-tree","-r","--name-only",sha).splitlines()
    mentioned={line.strip().split()[0].rstrip(":") for line in log.splitlines() if "/" in line}
    paths=[p for p in paths if p.endswith(".py") and not p.startswith(("tests/",".github/",".aios/","secrets/"))]
    paths.sort(key=lambda p:(0 if any(p in x for x in mentioned) else 1,p))
    out={}; used=0
    for p in paths:
        if len(out)>=MAX_SOURCE_FILES or used>=MAX_SOURCE_BYTES: break
        raw=subprocess.run(["git","show",f"{sha}:{p}"],capture_output=True,text=True,check=False).stdout
        if not raw: continue
        raw=raw[:10000]
        out[p]=raw
        used+=len(raw.encode())
    for p in sorted(owned):
        if p.startswith(("tests/",".github/",".aios/","secrets/")) or not p.endswith(".py"):
            continue
        try:
            raw=Path(p).read_text(encoding="utf-8",errors="replace")[:10000]
        except OSError:
            continue
        out[p]=raw
    return out

def authority(root, run_id):
    """Load externally issued, durable AIOS authority; never mint authority here.

    The authority directory must be persistent and pre-provisioned by AIOS.
    This workload may consume a contract/permit, but cannot create its own.
    """
    authority_dir = os.environ.get("AIOS_REPAIR_AUTHORITY_DIR", "").strip()
    contract_id = os.environ.get("AIOS_REPAIR_CONTRACT_ID", "").strip()
    permit_id = os.environ.get("AIOS_REPAIR_PERMIT_ID", "").strip()
    if not authority_dir or not contract_id or not permit_id:
        raise RuntimeError(
            "authority_not_provisioned: require durable AIOS_REPAIR_AUTHORITY_DIR, "
            "AIOS_REPAIR_CONTRACT_ID and AIOS_REPAIR_PERMIT_ID; self-issued authority forbidden"
        )
    durable_root = Path(authority_dir).expanduser().resolve()
    if not durable_root.is_dir():
        raise RuntimeError("authority_directory_missing")
    if any(part in {"tmp", "temp", "temporary"} for part in durable_root.parts):
        raise RuntimeError("authority_directory_must_not_be_temporary")
    # Resolve and validate the exact persisted records BEFORE proposal generation.
    # This checks contract identity, capability registry, governing policy, and
    # permit-to-contract binding. Missing/corrupt/forged records fail closed.
    try:
        from core.authority import authorize
        authorize(str(durable_root), contract_id, permit_id)
    except Exception as exc:
        raise RuntimeError(
            f"authority_records_rejected:{type(exc).__name__}:{exc}"
        ) from exc
    return contract_id, permit_id, durable_root

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
    checkpoint_id=f"try-ci-repair:{run_id}"
    prior=get_checkpoint(request_id=checkpoint_id)
    try:
        start_attempt=select_resume_attempt(
            prior, repository="yanhul/try", sha=base, max_attempts=MAX_ATTEMPTS
        )
    except RepairCheckpointError as exc:
        # A runner may disappear after a mutation but before recording its receipt.
        # Convert the durable WORKING marker into an explicit UNKNOWN/BLOCKED state;
        # never infer success or automatically replay an uncertain mutation.
        if is_interrupted_working_checkpoint(
            prior, repository="yanhul/try", sha=base
        ):
            reason = "interrupted_attempt_outcome_unknown; reconciliation_required"
            persist_checkpoint(
                request_id=checkpoint_id, repository="yanhul/try", sha=base,
                attempt=prior["attempt"], phase=prior["phase"], state="BLOCKED", reason=reason,
            )
            unknown = {
                "status": "UNKNOWN", "attempt": prior["attempt"], "phase": prior["phase"],
                "reason": reason, "reconciliation_required": True,
            }
            Path("repair-result.json").write_text(
                json.dumps(unknown, indent=2, sort_keys=True), encoding="utf-8"
            )
            print(json.dumps(unknown, sort_keys=True))
            return 2
        raise
    try:
        cid, pid, aios = authority(Path("."), run_id)
    except Exception as exc:
        reason=f"authority_gate_blocked:{type(exc).__name__}:{exc}"[:1000]
        persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                           attempt=max(1, int((prior or {}).get("attempt", 1))),
                           phase="DECIDE", state="BLOCKED", reason=reason)
        blocked={"status":"BLOCKED","reason":reason,"authority_required":True}
        Path("repair-result.json").write_text(json.dumps(blocked,indent=2,sort_keys=True),encoding="utf-8")
        print(json.dumps(blocked,sort_keys=True))
        return 2
    worker=AgentRepairWorker(Path("."),object(),allowed_test_commands=(("python","-m","pytest","-q"),),
                             timeout_seconds=900,aios_dir=aios,contract_id=cid,permit_id=pid,actor="try-autonomous-repair")
    owned=frozenset()
    if start_attempt == 1:
        persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                           attempt=1, phase="OBSERVE", state="WORKING")
    for attempt in range(start_attempt,MAX_ATTEMPTS+1):
        failure["attempt"]=attempt
        if attempt > 1:
            persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                               attempt=attempt, phase="RESUME", state="WORKING")
            persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                               attempt=attempt, phase="OBSERVE", state="WORKING")
            evidence=research_run(failure)
            failure["repair_research_evidence"]=evidence
            if evidence.get("status") not in {"EVIDENCE_COLLECTED","NO_EVIDENCE"}:
                reason=str(evidence.get("reason","research_hold"))
                persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                                   attempt=attempt, phase="OBSERVE", state="BLOCKED", reason=reason)
                results.append({"attempt":attempt,"status":"HOLD","reason":reason})
                break
        req_id=f"try-ci-repair:{run_id}:{attempt}"
        persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                           attempt=attempt, phase="DECIDE", state="WORKING")
        try:
            proposal=propose(request_id=req_id,repository="yanhul/try",sha=base,attempt=attempt,
                              failure=failure,source=source_snapshot(base,log,owned))
        except TryRepairProviderError as exc:
            proposal={"status":"HOLD","reason":str(exc)}
        except Exception as exc:
            proposal={"status":"HOLD","reason":f"proposal_stage_error:{type(exc).__name__}:{exc}"[:1000]}
        Path(f"repair-proposal-{attempt}.json").write_text(json.dumps(proposal,indent=2,sort_keys=True),encoding="utf-8")
        if proposal.get("status")=="HOLD":
            reason=str(proposal.get("reason") or "provider_hold")
            persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                               attempt=attempt, phase="DECIDE", state="BLOCKED", reason=reason)
            results.append({"attempt":attempt,"status":"HOLD","reason":reason})
            break
        persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                           attempt=attempt, phase="PROPOSE", state="WORKING")
        files=tuple(ProposedFile(x["path"],x["content"]) for x in proposal["files"])
        current_phase="PROPOSE"
        try:
            applied=worker.apply_via_aios(base_sha=base,files=files,
                logical_operation_id=req_id,allowed_dirty_paths=owned)
            owned=frozenset(set(owned)|{x.path for x in files})
            current_phase="VERIFY"
            persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                               attempt=attempt, phase="VERIFY", state="WORKING")
            tested=worker.test()
        except Exception as exc:
            reason=f"{type(exc).__name__}:{exc}"[:1000]
            persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                               attempt=attempt, phase=current_phase, state="BLOCKED", reason=reason)
            results.append({"attempt":attempt,"status":"BLOCKED","reason":reason})
            if attempt == MAX_ATTEMPTS:
                break
            continue
        if tested.status=="PASS" and not tested.evidence_refs:
            reason="test_pass_without_evidence_refs"
            persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                               attempt=attempt, phase="VERIFY", state="BLOCKED", reason=reason)
            results.append({"attempt":attempt,"status":"HOLD","reason":reason})
            break
        result={"attempt":attempt,"status":tested.status,"proposal":proposal,"apply":dict(applied),
                "test":{"status":tested.status,"evidence_refs":list(tested.evidence_refs),"details":dict(tested.details)},
                "research_evidence_digest":evidence.get("evidence_digest")}
        results.append(result)
        Path(f"repair-result-{attempt}.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
        if tested.status=="PASS":
            result_path=Path("repair-result.json")
            result_path.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
            digest=hashlib.sha256(result_path.read_bytes()).hexdigest()
            persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                               attempt=attempt, phase="PERSIST", state="WORKING")
            persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                               attempt=attempt, phase="PERSIST", state="DONE", evidence_digest=digest)
            print(json.dumps({"status":"PASS","attempt":attempt,"evidence_digest":digest}))
            return 0
        persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                           attempt=attempt, phase="VERIFY", state="BLOCKED",
                           reason=f"verification_{tested.status}")
        details=tested.details.get("results",[]) if tested.details else []
        log=(details[-1].get("stderr_tail","") if details else "")[-80000:]
        failure["ci_failure_log_tail"]=log
        failure["previous_repair_result"]=result
    Path("repair-result.json").write_text(json.dumps({"status":"FAIL","attempts":results},indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps({"status":"FAIL","attempts":len(results)}))
    return 2

if __name__=="__main__":
    raise SystemExit(main())
