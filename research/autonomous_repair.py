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
    if is_reconciliation_blocked_checkpoint(prior, repository=repository, sha=sha):
        raise RepairCheckpointError("checkpoint_reconciliation_required")
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


def is_reconciliation_blocked_checkpoint(prior, *, repository, sha):
    """Never retry an interrupted mutation until an independent reconciler clears it."""
    return (
        isinstance(prior, dict)
        and prior.get("state") == "BLOCKED"
        and prior.get("repository") == repository
        and prior.get("sha") == sha.lower()
        and "reconciliation_required" in str(prior.get("reason", ""))
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

def _verify_preflight_receipt(root, contract_id, permit_id, run_id):
    """Bind the isolated HMAC verifier's receipt to the exact persisted records."""
    receipt_path = os.environ.pop("AIOS_REPAIR_AUTHORITY_GATE_RECEIPT", "").strip()
    if not receipt_path:
        raise RuntimeError("authority_preflight_receipt_missing")
    try:
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("authority_preflight_receipt_unavailable") from exc
    if (
        receipt.get("schema") != 1
        or receipt.get("verified") is not True
        or receipt.get("run_id") != str(run_id)
        or receipt.get("authority_root") != str(root)
        or receipt.get("contract_id") != contract_id
        or receipt.get("permit_id") != permit_id
    ):
        raise RuntimeError("authority_preflight_receipt_identity_mismatch")
    for kind, record_id, field in (
        ("contracts", contract_id, "contract_sha256"),
        ("permits", permit_id, "permit_sha256"),
        ("attestations", permit_id, "attestation_sha256"),
    ):
        directory = (root / "authority" / kind).resolve()
        record_path = (directory / (record_id + ".json")).resolve()
        try:
            record_path.relative_to(directory)
        except ValueError as exc:
            raise RuntimeError("authority_record_path_escape") from exc
        try:
            digest = hashlib.sha256(record_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeError(f"authority_record_unavailable:{kind}") from exc
        if receipt.get(field) != digest:
            raise RuntimeError(f"authority_preflight_record_digest_mismatch:{kind}")


def authority(root, run_id):
    """Load preflight-verified durable AIOS authority; never mint authority here.

    HMAC verification runs in a separate workflow step/process so its secret is
    never present in the controller process that later launches untrusted tests.
    """
    authority_dir = os.environ.pop("AIOS_REPAIR_AUTHORITY_DIR", "").strip()
    contract_id = os.environ.pop("AIOS_REPAIR_CONTRACT_ID", "").strip()
    permit_id = os.environ.pop("AIOS_REPAIR_PERMIT_ID", "").strip()
    if not authority_dir or not contract_id or not permit_id:
        raise RuntimeError(
            "authority_not_provisioned: require durable AIOS_REPAIR_AUTHORITY_DIR, "
            "AIOS_REPAIR_CONTRACT_ID and AIOS_REPAIR_PERMIT_ID; self-issued authority forbidden"
        )
    durable_root = Path(authority_dir).expanduser().resolve()
    if not durable_root.is_dir():
        raise RuntimeError("authority_directory_missing")
    if any(part.lower() in {"tmp", "temp", "temporary"} for part in durable_root.parts):
        raise RuntimeError("authority_directory_must_not_be_temporary")
    try:
        _verify_preflight_receipt(durable_root, contract_id, permit_id, run_id)
        from core.authority import authorize, load_contract, load_permit

        authorize(str(durable_root), contract_id, permit_id)
        contract = load_contract(str(durable_root), contract_id)
        load_permit(str(durable_root), permit_id)
        if contract.get("task_id") != f"try-ci-repair-{run_id}":
            raise ValueError("contract_task_id_mismatch")
        if contract.get("actor") != "try-autonomous-repair":
            raise ValueError("contract_actor_mismatch")
        if contract.get("scope") != "repository":
            raise ValueError("contract_scope_mismatch")
        if "repo_patch@1" not in contract.get("capabilities", []):
            raise ValueError("contract_patch_capability_missing")
        if "external_effect" not in contract.get("allowed_effects", []):
            raise ValueError("contract_patch_effect_not_allowed")
        attempt_budget = contract.get("max_attempts")
        if (isinstance(attempt_budget, bool) or not isinstance(attempt_budget, int)
                or not 1 <= attempt_budget <= MAX_ATTEMPTS):
            raise ValueError("contract_attempt_budget_exceeds_runner_limit")
    except Exception as exc:
        raise RuntimeError(
            f"authority_records_rejected:{type(exc).__name__}:{exc}"
        ) from exc
    return contract_id, permit_id, durable_root

def resolve_terminal_evidence(aios_root, evidence_refs, *, run_id, base_sha, applied, contract_id, permit_id):
    """Resolve independent AIOS receipts and test evidence before terminal promotion.

    Evidence files are expected under the persistent AIOS root's evidence/ directory.
    Missing records, invalid digests, identity/lineage mismatches, or an absent
    persisted successful effect all fail closed.
    """
    import re
    from core.evidence import verify_evidence

    if not isinstance(applied, dict):
        return "terminal_receipt_blocked:apply_result_not_mapping"
    effect_id = applied.get("effect_id")
    if not isinstance(effect_id, str) or not re.fullmatch(r"EF-[0-9a-f]{64}", effect_id):
        return "terminal_receipt_blocked:missing_or_invalid_effect_id"
    effects_dir = (Path(aios_root) / "effects").resolve()
    effect_path = (effects_dir / (effect_id + ".json")).resolve()
    try:
        effect_path.relative_to(effects_dir)
    except ValueError:
        return "terminal_receipt_blocked:persisted_effect_path_escape"
    try:
        effect = json.loads(effect_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"terminal_receipt_blocked:persisted_effect_unavailable:{type(exc).__name__}"
    if not isinstance(effect, dict):
        return "terminal_receipt_blocked:persisted_effect_not_mapping"
    if effect.get("effect_id") != effect_id or effect.get("state") != "OBSERVED_SUCCESS":
        return "terminal_receipt_blocked:effect_not_persisted_observed_success"
    if (effect.get("contract_id") != contract_id or effect.get("permit_id") != permit_id
            or effect.get("actor") != "try-autonomous-repair"):
        return "terminal_receipt_blocked:effect_authority_identity_mismatch"
    observation = effect.get("provider_observation")
    if not isinstance(observation, dict):
        return "terminal_receipt_blocked:provider_observation_missing"
    if observation.get("attempt_id") != effect.get("attempt_id") or observation.get("provider") != effect.get("provider"):
        return "terminal_receipt_blocked:provider_observation_lineage_mismatch"
    effect_evidence = observation.get("evidence")
    if not isinstance(effect_evidence, dict) or not verify_evidence(effect_evidence):
        return "terminal_receipt_blocked:effect_evidence_digest_invalid"
    if effect_evidence.get("provider") != effect.get("provider"):
        return "terminal_receipt_blocked:effect_evidence_provider_mismatch"
    if effect_evidence.get("run_id") != effect.get("attempt_id"):
        return "terminal_receipt_blocked:effect_evidence_attempt_mismatch"
    if not isinstance(evidence_refs, (list, tuple)) or not evidence_refs:
        return "terminal_evidence_blocked:no_test_evidence_refs"
    if any(not isinstance(ref, str) or not re.fullmatch(r"EV-[A-Za-z0-9_-]{1,120}", ref)
           for ref in evidence_refs):
        return "terminal_evidence_blocked:invalid_evidence_id"
    if len(set(evidence_refs)) != len(evidence_refs):
        return "terminal_evidence_blocked:duplicate_evidence_refs"
    evidence_dir = (Path(aios_root) / "evidence").resolve()
    # A syntactically safe EV-* ID is not enough: reject symlink/path redirection
    # so the resolver cannot accidentally validate a record outside the AIOS store.
    def load_evidence(ref):
        if not isinstance(ref, str) or not re.fullmatch(r"EV-[A-Za-z0-9_-]{1,120}", ref):
            raise ValueError("invalid_evidence_id")
        path = (evidence_dir / (ref + ".json")).resolve()
        try:
            path.relative_to(evidence_dir)
        except ValueError as exc:
            raise ValueError("evidence_record_path_escape") from exc
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("evidence_id") != ref or not verify_evidence(record):
            raise ValueError("record_digest_or_identity_invalid")
        return record

    seen = set()
    for ref in evidence_refs:
        try:
            record = load_evidence(ref)
        except (OSError, ValueError) as exc:
            return f"terminal_evidence_blocked:record_unavailable_or_invalid:{ref}:{type(exc).__name__}:{exc}"
        if ref in seen:
            return "terminal_evidence_blocked:duplicate_evidence_refs"
        seen.add(ref)
        if record.get("run_id") != str(run_id):
            return f"terminal_evidence_blocked:run_identity_mismatch:{ref}"
        if record.get("level") not in {"VERIFIED_DIGITAL", "PROMOTED"}:
            return f"terminal_evidence_blocked:verification_level_insufficient:{ref}"
        source_ref = record.get("source_ref")
        artifact_ref = record.get("artifact_ref")
        lineage = " ".join(value for value in (source_ref, artifact_ref) if isinstance(value, str))
        # Match the complete 40-hex SHA token, not a substring of a longer or
        # otherwise malformed identifier. The evidence digest authenticates the
        # record, while this independently checks that it names this exact base.
        if not re.search(r"(?<![0-9a-f])" + re.escape(base_sha.lower()) + r"(?![0-9a-f])", lineage.lower()):
            return f"terminal_evidence_blocked:base_sha_lineage_missing:{ref}"
        claim = str(record.get("claim") or "").lower()
        if not any(token in claim for token in ("test", "pytest", "verification")):
            return f"terminal_evidence_blocked:claim_not_test_verification:{ref}"
        parent_id = record.get("parent_evidence_id")
        ancestors = {ref}
        while parent_id is not None:
            if not isinstance(parent_id, str) or not re.fullmatch(r"EV-[A-Za-z0-9_-]{1,120}", parent_id):
                return f"terminal_evidence_blocked:parent_evidence_invalid:{ref}:invalid_evidence_id"
            if parent_id in ancestors:
                return f"terminal_evidence_blocked:parent_evidence_cycle:{ref}"
            ancestors.add(parent_id)
            try:
                parent = load_evidence(parent_id)
            except (OSError, ValueError, TypeError) as exc:
                return f"terminal_evidence_blocked:parent_evidence_invalid:{ref}:{type(exc).__name__}:{exc}"
            if parent.get("run_id") != str(run_id):
                return f"terminal_evidence_blocked:parent_evidence_lineage_mismatch:{ref}"
            parent_lineage = " ".join(
                value for value in (parent.get("source_ref"), parent.get("artifact_ref"))
                if isinstance(value, str)
            )
            if not re.search(
                r"(?<![0-9a-f])" + re.escape(base_sha.lower()) + r"(?![0-9a-f])",
                parent_lineage.lower(),
            ):
                return f"terminal_evidence_blocked:parent_base_sha_lineage_missing:{ref}"
            parent_id = parent.get("parent_evidence_id")
    return None


def main():
    # Keep the provider credential in controller memory; expose it only during a proposal call.
    provider_token = os.environ.pop("TRY_REPAIR_PROVIDER_TOKEN", "")
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
        if is_reconciliation_blocked_checkpoint(
            prior, repository="yanhul/try", sha=base
        ):
            unknown = {
                "status": "UNKNOWN", "attempt": prior["attempt"], "phase": prior.get("phase"),
                "reason": "interrupted_attempt_outcome_unknown; reconciliation_required",
                "reconciliation_required": True,
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
            if provider_token:
                os.environ["TRY_REPAIR_PROVIDER_TOKEN"] = provider_token
            proposal=propose(request_id=req_id,repository="yanhul/try",sha=base,attempt=attempt,
                              failure=failure,source=source_snapshot(base,log,owned))
        except TryRepairProviderError as exc:
            proposal={"status":"HOLD","reason":str(exc)}
        except Exception as exc:
            proposal={"status":"HOLD","reason":f"proposal_stage_error:{type(exc).__name__}:{exc}"[:1000]}
        finally:
            # The verification subprocess runs later and must never inherit this credential.
            os.environ.pop("TRY_REPAIR_PROVIDER_TOKEN", None)
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
        if tested.status=="PASS":
            reason = resolve_terminal_evidence(
                aios, tested.evidence_refs, run_id=run_id, base_sha=base,
                applied=applied, contract_id=cid, permit_id=pid,
            )
            if reason:
                blocked={"status":"BLOCKED","attempt":attempt,"reason":reason,
                         "test_status":"PASS","test_evidence_refs":list(tested.evidence_refs)}
                Path("repair-result.json").write_text(json.dumps(blocked,indent=2,sort_keys=True),encoding="utf-8")
                persist_checkpoint(request_id=checkpoint_id, repository="yanhul/try", sha=base,
                                   attempt=attempt, phase="PERSIST", state="BLOCKED", reason=reason)
                print(json.dumps({"status":"BLOCKED","attempt":attempt,"reason":reason},sort_keys=True))
                return 2
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
