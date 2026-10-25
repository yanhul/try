from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from research import lineage_engine
from research.autonomous_hypothesis import canonical_hash, validate_candidate
from research.hypothesis_novelty import novelty_metadata

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = "CANDIDATE_REGISTRATION"
REJECTED = {"REJECT", "REJECT_BC"}
HARD_PROVIDER_ERRORS = (
    "provider_quota_exhausted",
    "provider_rpd_budget_exhausted",
    "provider_project_id_missing",
    "provider_not_configured",
    "gemini_api_key",
)


def _read(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_paths(root: Path):
    return root / "research" / "autonomous_candidates"


def _registration_records(records: list[dict], bc: int) -> list[dict]:
    return [
        item for item in records
        if item.get("registration_type") == REGISTRATION
        and int(item.get("generation", -1)) == bc
    ]


def validate_queued_candidate(root: Path = ROOT, require_registration: bool = False) -> dict:
    research = root / "research"
    state = _read(research / "bc_lifecycle_state.json", {})
    policy = _read(research / "campaign_policy.json", {})
    queue = _read(research / "bc_queue.json", [])
    if not isinstance(state, dict) or not isinstance(policy, dict) or not isinstance(queue, list):
        raise ValueError("DURABLE_QUEUE_SCHEMA_INVALID")
    if state.get("campaign_id") != policy.get("campaign_id"):
        raise ValueError("DURABLE_QUEUE_CAMPAIGN_MISMATCH")
    if state.get("campaign_terminal") is True or state.get("terminal") is True:
        raise ValueError("DURABLE_QUEUE_CAMPAIGN_TERMINAL")
    checkpoint = state.get("checkpoint_seq")
    if not isinstance(checkpoint, int) or isinstance(checkpoint, bool) or checkpoint < 0:
        raise ValueError("DURABLE_QUEUE_CHECKPOINT_INVALID")
    bc = state.get("next_bc")
    if not isinstance(bc, int) or isinstance(bc, bool) or bc <= 0:
        raise ValueError("DURABLE_QUEUE_NEXT_BC_INVALID")
    matches = [item for item in queue if isinstance(item, dict) and item.get("bc") == bc]
    if len(matches) != 1:
        raise ValueError("DURABLE_QUEUE_BC_NOT_UNIQUE")
    queued = matches[0]
    parent = bc - 1
    if queued.get("parent_bc") != parent or state.get("current_bc") != bc:
        raise ValueError("DURABLE_QUEUE_CHECKPOINT_BINDING_MISMATCH")

    candidate_path = _candidate_paths(root) / f"BC{bc}.json"
    candidate = _read(candidate_path, {})
    if not isinstance(candidate, dict) or not candidate:
        raise ValueError("DURABLE_QUEUE_CANDIDATE_MISSING")
    ok, reason = validate_candidate(candidate, bc, parent)
    if not ok:
        raise ValueError(f"DURABLE_QUEUE_CANDIDATE_INVALID:{reason}")
    candidate_hash = canonical_hash(candidate)
    if candidate.get("candidate_hash") != candidate_hash or queued.get("candidate_hash") != candidate_hash:
        raise ValueError("DURABLE_QUEUE_CANDIDATE_HASH_MISMATCH")
    for field in ("hypothesis_id", "discovery_spec", "evidence_sources", "novelty_key", "oos_selection_used"):
        if queued.get(field) != candidate.get(field):
            raise ValueError(f"DURABLE_QUEUE_CANDIDATE_BINDING_MISMATCH:{field}")
    if candidate.get("oos_selection_used") is not False or queued.get("oos_selection_used") is not False:
        raise ValueError("DURABLE_QUEUE_OOS_SELECTION_FORBIDDEN")

    parent_candidate_path = _candidate_paths(root) / f"BC{parent}.json"
    parent_candidate = _read(parent_candidate_path, {})
    failure_path = research / "failure_analysis" / f"BC{parent}.json"
    failure = _read(failure_path, {})
    validation_path = research / f"bc{parent}_validation_result.json"
    parent_validation = _read(validation_path, {})
    if not parent_candidate or not failure or not parent_validation:
        raise ValueError("DURABLE_QUEUE_PARENT_EVIDENCE_MISSING")
    if failure.get("bc") != parent or failure.get("decision") not in REJECTED:
        raise ValueError("DURABLE_QUEUE_PARENT_FAILURE_INVALID")
    if failure.get("candidate_hash") != parent_candidate.get("candidate_hash"):
        raise ValueError("DURABLE_QUEUE_PARENT_FAILURE_HASH_MISMATCH")
    if parent_validation.get("bc") != parent or parent_validation.get("candidate_hash") != parent_candidate.get("candidate_hash"):
        raise ValueError("DURABLE_QUEUE_PARENT_VALIDATION_BINDING_MISMATCH")
    if parent_validation.get("oos_executed") is not False or parent_validation.get("oos_selection_used") is not False:
        raise ValueError("DURABLE_QUEUE_PARENT_EVIDENCE_NOT_PRE_OOS")
    history = [item for item in state.get("history", []) if isinstance(item, dict) and item.get("bc") == parent]
    if not any(item.get("decision") in REJECTED and item.get("candidate_hash") == parent_candidate.get("candidate_hash") for item in history):
        raise ValueError("DURABLE_QUEUE_PARENT_HISTORY_MISMATCH")
    if failure.get("oos_selection_used") is not False:
        raise ValueError("DURABLE_QUEUE_PARENT_OOS_SELECTION_FORBIDDEN")

    spec = candidate.get("discovery_spec") or {}
    family = spec.get("mechanism_family")
    if not family:
        raise ValueError("DURABLE_QUEUE_FAMILY_MISSING")
    memory_path = research / "discovery" / ".search_memory.json"
    memory = _read(memory_path, {})
    if memory.get("last_selection_bc") != bc or memory.get("last_selected_family") != family:
        raise ValueError("DURABLE_QUEUE_SELECTED_FAMILY_MISMATCH")
    survivors_path = research / "discovery" / "survivors.json"
    survivors_doc = _read(survivors_path, {})
    survivors = survivors_doc.get("survivors", []) if isinstance(survivors_doc, dict) else []
    evidence_sources = candidate.get("evidence_sources", [])
    matching_survivors = [
        item for item in survivors
        if isinstance(item, dict)
        and item.get("family") == family
        and item.get("source_url") in evidence_sources
    ]
    if len(matching_survivors) != 1:
        raise ValueError("DURABLE_QUEUE_SELECTED_SURVIVOR_MISMATCH")
    survivor = matching_survivors[0]
    taxonomy = (survivor.get("lineage") or {}).get("taxonomy") or {}
    if taxonomy.get("status") != "EXECUTABLE" or taxonomy.get("canonical_family") != family:
        raise ValueError("DURABLE_QUEUE_SELECTED_SURVIVOR_NOT_EXECUTABLE")

    novelty = novelty_metadata(candidate)
    novelty_key = novelty.get("novelty_key")
    if candidate.get("novelty_key") != novelty_key:
        raise ValueError("DURABLE_QUEUE_NOVELTY_KEY_MISMATCH")
    registry = memory.get("candidates", {})
    if not isinstance(registry, dict):
        raise ValueError("DURABLE_QUEUE_NOVELTY_REGISTRY_INVALID")
    if novelty_key in registry or any(
        isinstance(item, dict) and item.get("candidate_hash") == candidate_hash
        for item in registry.values()
    ):
        raise ValueError("DURABLE_QUEUE_NOVELTY_REPLAY")
    for path in _candidate_paths(root).glob("BC*.json"):
        try:
            prior_bc = int(path.stem[2:])
        except ValueError:
            continue
        if prior_bc >= bc:
            continue
        prior = _read(path, {})
        if not isinstance(prior, dict):
            continue
        if prior.get("candidate_hash") == candidate_hash:
            raise ValueError("DURABLE_QUEUE_CANDIDATE_HASH_REPLAY")
        prior_key = prior.get("novelty_key")
        if not prior_key:
            try:
                prior_key = novelty_metadata(prior).get("novelty_key")
            except Exception:
                prior_key = None
        if prior_key and prior_key == novelty_key:
            raise ValueError(f"DURABLE_QUEUE_NOVELTY_REPLAY:BC{prior_bc}")

    lineage = lineage_engine.read_lineage()
    records = _registration_records(lineage, bc)
    if records:
        if len(records) != 1 or records[0].get("config_hash") != candidate_hash:
            raise ValueError("DURABLE_QUEUE_REGISTRATION_LINEAGE_CONFLICT")
        result = records[0].get("result", {})
        if (
            records[0].get("selected_family") != family
            or records[0].get("selected_survivor_id") != survivor.get("candidate_id")
            or records[0].get("novelty_key") != novelty_key
            or result.get("candidate_hash") != candidate_hash
        ):
            raise ValueError("DURABLE_QUEUE_REGISTRATION_LINEAGE_BINDING_MISMATCH")
        registered = True
    else:
        if any(int(item.get("generation", -1)) == bc for item in lineage if isinstance(item, dict)):
            raise ValueError("DURABLE_QUEUE_RESULT_EXISTS_WITHOUT_PRE_IS_REGISTRATION")
        registered = False
    if require_registration and not registered:
        raise ValueError("DURABLE_QUEUE_REGISTRATION_LINEAGE_MISSING")

    # No IS/validation/OOS artifact for this candidate may predate registration.
    for relative in (
        f"bc{bc}_is_result.json",
        f"bc{bc}_validation_result.json",
        f"frozen_candidates/BC{bc}.json",
        f"oos/BC{bc}_oos_result.json",
        f"oos/BC{bc}_oos_result_receipt.json",
    ):
        if (research / relative).exists() and not registered:
            raise ValueError(f"DURABLE_QUEUE_EVALUATION_PRECEDED_REGISTRATION:{relative}")
    return {
        "bc": bc,
        "parent_bc": parent,
        "checkpoint_seq": checkpoint,
        "campaign_id": state["campaign_id"],
        "candidate": candidate,
        "candidate_hash": candidate_hash,
        "failure": failure,
        "family": family,
        "survivor": survivor,
        "novelty_key": novelty_key,
        "registered": registered,
        "state": state,
    }


def validate_discovery_frontier(root: Path = ROOT) -> dict:
    research = root / "research"
    state = _read(research / "bc_lifecycle_state.json", {})
    policy = _read(research / "campaign_policy.json", {})
    queue = _read(research / "bc_queue.json", [])
    if state.get("campaign_id") != policy.get("campaign_id"):
        raise ValueError("CONTINUATION_DISCOVERY_CAMPAIGN_MISMATCH")
    if state.get("campaign_terminal") or state.get("terminal"):
        raise ValueError("CONTINUATION_DISCOVERY_CAMPAIGN_TERMINAL")
    error = str(state.get("last_error") or "").lower()
    if state.get("phase") in {"HOLD", "WAIT_RETRY"} or any(marker in error for marker in HARD_PROVIDER_ERRORS):
        raise ValueError("CONTINUATION_DISCOVERY_HARD_BLOCKER")
    if not isinstance(queue, list) or queue:
        raise ValueError("CONTINUATION_DISCOVERY_QUEUE_ALREADY_PRESENT")
    last_bc = state.get("last_bc")
    if not isinstance(last_bc, int) or isinstance(last_bc, bool) or state.get("next_bc") != last_bc + 1:
        raise ValueError("CONTINUATION_DISCOVERY_FRONTIER_INVALID")
    if not isinstance(state.get("checkpoint_seq"), int) or state["checkpoint_seq"] < 0:
        raise ValueError("CONTINUATION_DISCOVERY_CHECKPOINT_INVALID")
    candidate = _read(_candidate_paths(root) / f"BC{last_bc}.json", {})
    failure = _read(research / "failure_analysis" / f"BC{last_bc}.json", {})
    validation = _read(research / f"bc{last_bc}_validation_result.json", {})
    if not candidate or not failure or not validation:
        raise ValueError("CONTINUATION_DISCOVERY_FAILURE_EVIDENCE_MISSING")
    candidate_hash = candidate.get("candidate_hash")
    if failure.get("decision") not in REJECTED or failure.get("bc") != last_bc:
        raise ValueError("CONTINUATION_DISCOVERY_FAILURE_DECISION_INVALID")
    if failure.get("candidate_hash") != candidate_hash or validation.get("candidate_hash") != candidate_hash:
        raise ValueError("CONTINUATION_DISCOVERY_CANDIDATE_BINDING_INVALID")
    if failure.get("oos_selection_used") is not False or validation.get("oos_selection_used") is not False or validation.get("oos_executed") is not False:
        raise ValueError("CONTINUATION_DISCOVERY_OOS_SELECTION_FORBIDDEN")
    if (_candidate_paths(root) / f"BC{last_bc + 1}.json").exists():
        raise ValueError("CONTINUATION_DISCOVERY_NEXT_CANDIDATE_ALREADY_EXISTS")
    if not any(
        isinstance(item, dict)
        and item.get("experiment_id") == f"BC{last_bc}:{candidate_hash}"
        and item.get("config_hash") == candidate_hash
        for item in lineage_engine.read_lineage()
    ):
        raise ValueError("CONTINUATION_DISCOVERY_LINEAGE_NOT_PERSISTED")
    return {
        "bc": last_bc,
        "next_bc": last_bc + 1,
        "checkpoint_seq": state["checkpoint_seq"],
        "campaign_id": state["campaign_id"],
        "candidate_hash": candidate_hash,
        "state": state,
        "failure": failure,
    }


def register_candidate_lineage(root: Path = ROOT) -> str:
    bundle = validate_queued_candidate(root, require_registration=False)
    if bundle["registered"]:
        return "ALREADY_REGISTERED"
    research = root / "research"
    validation = _read(research / f"bc{bundle['parent_bc']}_validation_result.json", {})
    data_hash = (validation.get("dataset") or {}).get("sha256")
    if not isinstance(data_hash, str) or len(data_hash) != 64:
        raise ValueError("DURABLE_QUEUE_PARENT_DATA_HASH_MISSING")
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
    except Exception:
        revision = "workflow-main"
    candidate = bundle["candidate"]
    record = {
        "experiment_id": f"BC{bundle['bc']}:REGISTRATION:{bundle['candidate_hash']}",
        "generation": bundle["bc"],
        "parent_artifacts": [
            f"research/failure_analysis/BC{bundle['parent_bc']}.json",
            f"research/bc{bundle['parent_bc']}_validation_result.json",
            "research/discovery/survivors.json",
            "research/discovery/.search_memory.json",
            "research/bc_queue.json",
            f"research/autonomous_candidates/BC{bundle['bc']}.json",
        ],
        "hypothesis": candidate.get("hypothesis_id", "UNKNOWN"),
        "change": candidate.get("conceptual_change", "UNKNOWN"),
        "code_revision": revision or "workflow-main",
        "config_hash": bundle["candidate_hash"],
        "data_hash": data_hash,
        "evaluator": "research.candidate_registration.pre_IS_gate",
        "result": {
            "status": "CANDIDATE_REGISTERED",
            "bc": bundle["bc"],
            "parent_bc": bundle["parent_bc"],
            "candidate_hash": bundle["candidate_hash"],
            "family": bundle["family"],
            "novelty_key": bundle["novelty_key"],
            "parent_failure_decision": bundle["failure"].get("decision"),
            "selected_survivor_id": bundle["survivor"].get("candidate_id"),
        },
        "verdict": "CANDIDATE_REGISTERED",
        "decision": "REGISTERED_PRE_IS",
        "evidence": [
            f"research/autonomous_candidates/BC{bundle['bc']}.json",
            f"research/failure_analysis/BC{bundle['parent_bc']}.json",
            f"research/bc{bundle['parent_bc']}_validation_result.json",
            "research/discovery/survivors.json",
            "research/discovery/.search_memory.json",
        ],
        "findings": [],
        "constraints": ["IS_THEN_VALIDATION", "OOS_EVALUATION_ONLY", "NO_REPLAY"],
        "claims": [],
        "registration_type": REGISTRATION,
        "selected_family": bundle["family"],
        "selected_survivor_id": bundle["survivor"].get("candidate_id"),
        "novelty_key": bundle["novelty_key"],
    }
    lineage_engine.append_experiment(record)
    return "REGISTERED"


def _assert_main_persisted(root: Path) -> None:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    if not head or head != remote:
        raise ValueError("CONTINUATION_AUTHORIZATION_MAIN_PERSISTENCE_UNPROVEN")


def authorize_pending(root: Path = ROOT, source_run_id: int = 0, kind: str = "PROGRESS", require_main: bool = True) -> dict:
    if not isinstance(source_run_id, int) or isinstance(source_run_id, bool) or source_run_id <= 0:
        raise ValueError("CONTINUATION_AUTHORIZATION_SOURCE_RUN_ID_INVALID")
    if require_main:
        _assert_main_persisted(root)
    if kind == "PROGRESS":
        bundle = validate_queued_candidate(root, require_registration=True)
        state = bundle["state"]
        bc = bundle["bc"]
        intent = {
            "schema_version": 1,
            "status": "PENDING",
            "authorization_kind": "PROGRESS",
            "campaign_id": bundle["campaign_id"],
            "next_bc": bc,
            "current_bc": bc,
            "checkpoint_seq": bundle["checkpoint_seq"],
            "created_by_run_id": source_run_id,
            "target_ref": "main",
            "candidate_hash": bundle["candidate_hash"],
            "novelty_key": bundle["novelty_key"],
        }
    elif kind == "DISCOVERY":
        bundle = validate_discovery_frontier(root)
        state = bundle["state"]
        intent = {
            "schema_version": 1,
            "status": "PENDING",
            "authorization_kind": "DISCOVERY",
            "campaign_id": bundle["campaign_id"],
            "next_bc": bundle["next_bc"],
            "current_bc": state.get("current_bc"),
            "checkpoint_seq": bundle["checkpoint_seq"],
            "created_by_run_id": source_run_id,
            "target_ref": "main",
            "parent_failure_bc": bundle["bc"],
            "parent_candidate_hash": bundle["candidate_hash"],
        }
    elif kind == "RETRY":
        state = _read(root / "research" / "bc_lifecycle_state.json", {})
        error = str(state.get("last_error") or "").lower()
        if state.get("campaign_terminal") or state.get("terminal") or state.get("phase") != "WAIT_RETRY":
            raise ValueError("CONTINUATION_RETRY_STATE_INVALID")
        if any(marker in error for marker in HARD_PROVIDER_ERRORS):
            raise ValueError("CONTINUATION_RETRY_HARD_BLOCKER")
        if int(state.get("retry_count", 0)) >= 10:
            raise ValueError("CONTINUATION_RETRY_BUDGET_EXHAUSTED")
        intent = {
            "schema_version": 1,
            "status": "PENDING",
            "authorization_kind": "RETRY",
            "campaign_id": state.get("campaign_id"),
            "next_bc": state.get("next_bc"),
            "current_bc": state.get("current_bc"),
            "checkpoint_seq": state.get("checkpoint_seq"),
            "created_by_run_id": source_run_id,
            "target_ref": "main",
        }
    else:
        raise ValueError("CONTINUATION_AUTHORIZATION_KIND_INVALID")
    target = root / "research" / "continuation_intent.json"
    target.write_text(json.dumps(intent, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return intent


def status(root: Path = ROOT) -> str:
    try:
        bundle = validate_queued_candidate(root, require_registration=False)
    except Exception as queue_error:
        research = root / "research"
        state = _read(research / "bc_lifecycle_state.json", {})
        error = str(state.get("last_error") or "").lower()
        if state.get("phase") == "WAIT_RETRY" and not any(marker in error for marker in HARD_PROVIDER_ERRORS):
            if not state.get("campaign_terminal") and not state.get("terminal") and int(state.get("retry_count", 0)) < 10:
                return "RETRY_READY"
        try:
            validate_discovery_frontier(root)
            return "DISCOVERY_READY"
        except Exception:
            return f"BLOCKED:{queue_error}"
    return "READY" if bundle["registered"] else "REGISTRATION_REQUIRED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "register", "validate", "validate-discovery", "authorize"))
    parser.add_argument("--source-run-id", type=int, default=0)
    parser.add_argument("--kind", choices=("PROGRESS", "DISCOVERY", "RETRY"), default="PROGRESS")
    args = parser.parse_args()
    try:
        if args.command == "status":
            result = status()
            print(result)
            return 0 if not result.startswith("BLOCKED:") else 2
        if args.command == "register":
            print(register_candidate_lineage())
            return 0
        if args.command == "validate":
            bundle = validate_queued_candidate(require_registration=True)
            print(f"DURABLE_QUEUE_AUTHORIZED BC{bundle['bc']} checkpoint={bundle['checkpoint_seq']} candidate_hash={bundle['candidate_hash']}")
            return 0
        if args.command == "validate-discovery":
            bundle = validate_discovery_frontier()
            print(f"DISCOVERY_FRONTIER_AUTHORIZED parent_BC{bundle['bc']} next_BC{bundle['next_bc']} checkpoint={bundle['checkpoint_seq']}")
            return 0
        intent = authorize_pending(source_run_id=args.source_run_id, kind=args.kind)
        print(f"CONTINUATION_INTENT_PENDING kind={args.kind} BC{intent.get('next_bc')} checkpoint={intent.get('checkpoint_seq')}")
        return 0
    except Exception as exc:
        print(f"CONTINUATION_AUTHORIZATION_BLOCKED {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
