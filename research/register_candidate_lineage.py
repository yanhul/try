"""Validate and durably register a queued research candidate before evaluation.

This records provenance only. It never runs IS, validation, or OOS and never
changes candidate, failure, queue, checkpoint, or strategy evidence artifacts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from research.family_registry import require_executable
from research.hypothesis_novelty import novelty_metadata
from research.lineage_engine import append_experiment, read_lineage

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "research/bc_lifecycle_state.json"
QUEUE = ROOT / "research/bc_queue.json"
CANDIDATES = ROOT / "research/autonomous_candidates"
FAILURES = ROOT / "research/failure_analysis"
SEARCH_MEMORY = ROOT / "research/discovery/.search_memory.json"
SURVIVORS = ROOT / "research/discovery/survivors.json"
ABSORPTION = ROOT / "research/discovery/absorption_proof.json"
IMPLEMENTATION = ROOT / "research/discovery/implementation_absorption_proof.json"
DATA = ROOT / "data/BTCUSDT_1h.csv"


class RegistrationBlocked(ValueError):
    pass


def load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def emit_outputs(**values) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")


def validate_queued_candidate():
    state = load(STATE, {})
    queue = load(QUEUE, [])
    if not isinstance(state, dict) or not isinstance(queue, list):
        raise RegistrationBlocked("invalid_durable_state_or_queue")
    if not queue:
        return None

    next_bc = state.get("next_bc")
    current_bc = state.get("current_bc")
    if not isinstance(next_bc, int) or not isinstance(current_bc, int):
        raise RegistrationBlocked("invalid_current_or_next_bc")
    matches = [item for item in queue if isinstance(item, dict) and item.get("bc") == next_bc]
    if not matches:
        return None
    if len(matches) != 1:
        raise RegistrationBlocked(f"ambiguous_queue_entries_for_bc_{next_bc}")
    item = matches[0]
    bc = next_bc
    candidate_path = CANDIDATES / f"BC{bc}.json"
    candidate = load(candidate_path)
    if not isinstance(candidate, dict):
        raise RegistrationBlocked(f"missing_candidate_BC{bc}")
    candidate_hash = candidate.get("candidate_hash")
    if not candidate_hash or item.get("candidate_hash") != candidate_hash:
        raise RegistrationBlocked("queue_candidate_hash_mismatch")
    if candidate.get("bc") != bc or current_bc != bc:
        raise RegistrationBlocked("candidate_current_bc_mismatch")
    if state.get("campaign_id") != "BTCUSDT-1H-AUTONOMOUS-002":
        raise RegistrationBlocked("campaign_id_mismatch")
    if not isinstance(state.get("checkpoint_seq"), int) or state["checkpoint_seq"] < 0:
        raise RegistrationBlocked("invalid_checkpoint_seq")
    if candidate.get("parent_bc") != bc - 1 or item.get("parent_bc") != bc - 1:
        raise RegistrationBlocked("candidate_parent_bc_mismatch")
    for key in ("discovery_spec", "novelty_key", "evidence_sources", "hypothesis_id"):
        if item.get(key) != candidate.get(key):
            raise RegistrationBlocked(f"queue_candidate_{key}_mismatch")
    if candidate.get("is_testable") is not True or candidate.get("oos_selection_used") is not False:
        raise RegistrationBlocked("candidate_not_testable_or_oos_contaminated")
    if not isinstance(candidate.get("conceptual_change"), str) or not candidate["conceptual_change"].strip():
        raise RegistrationBlocked("candidate_single_change_missing")

    family = (candidate.get("discovery_spec") or {}).get("mechanism_family")
    if not isinstance(family, str) or not family:
        raise RegistrationBlocked("candidate_family_missing")
    try:
        require_executable(family)
    except ValueError as exc:
        raise RegistrationBlocked(str(exc)) from exc

    parent_bc = bc - 1
    failure_path = FAILURES / f"BC{parent_bc}.json"
    failure = load(failure_path)
    parent_candidate = load(CANDIDATES / f"BC{parent_bc}.json")
    parent_validation = load(ROOT / f"research/bc{parent_bc}_validation_result.json")
    if not isinstance(failure, dict) or failure.get("bc") != parent_bc:
        raise RegistrationBlocked("parent_failure_artifact_missing_or_mismatched")
    if failure.get("decision") not in {"REJECT", "REJECT_BC"}:
        raise RegistrationBlocked("parent_failure_not_rejected")
    if not isinstance(parent_candidate, dict) or not parent_candidate.get("candidate_hash"):
        raise RegistrationBlocked("parent_candidate_missing")
    if failure.get("candidate_hash") != parent_candidate.get("candidate_hash"):
        raise RegistrationBlocked("parent_failure_candidate_hash_mismatch")
    if not isinstance(parent_validation, dict) or parent_validation.get("candidate_hash") != parent_candidate.get("candidate_hash"):
        raise RegistrationBlocked("parent_validation_evidence_missing_or_mismatched")
    if parent_validation.get("validation_passed") is not False or parent_validation.get("oos_executed") is not False:
        raise RegistrationBlocked("parent_validation_is_not_a_pre_oos_rejection")

    memory = load(SEARCH_MEMORY)
    survivors_payload = load(SURVIVORS)
    absorption = load(ABSORPTION)
    implementation = load(IMPLEMENTATION)
    if not all(isinstance(value, dict) for value in (memory, survivors_payload, absorption, implementation)):
        raise RegistrationBlocked("discovery_lineage_artifacts_missing")
    if memory.get("last_selection_bc") != bc or memory.get("last_selected_family") != family:
        raise RegistrationBlocked("selected_family_record_mismatch")
    novelty = novelty_metadata(candidate).get("novelty_key")
    if not novelty or candidate.get("novelty_key") != novelty:
        raise RegistrationBlocked("candidate_novelty_key_mismatch")
    registry = memory.get("candidates")
    if not isinstance(registry, dict):
        raise RegistrationBlocked("prior_candidate_registry_missing")
    if novelty in registry:
        raise RegistrationBlocked("candidate_novelty_already_registered")

    sources = candidate.get("evidence_sources")
    if not isinstance(sources, list) or not sources:
        raise RegistrationBlocked("pre_oos_evidence_source_missing")
    survivor_list = survivors_payload.get("survivors")
    if not isinstance(survivor_list, list):
        raise RegistrationBlocked("discovery_survivor_registry_missing")
    survivor = next(
        (entry for entry in survivor_list
         if isinstance(entry, dict)
         and entry.get("family") == family
         and entry.get("source_url") in sources),
        None,
    )
    if survivor is None:
        raise RegistrationBlocked("candidate_not_bound_to_selected_discovery_survivor")
    source_id = survivor.get("candidate_id")
    absorbed = absorption.get("absorbed")
    implemented = implementation.get("implemented")
    if not isinstance(absorbed, list) or not any(
        isinstance(entry, dict)
        and entry.get("candidate_id") == source_id
        and entry.get("family") == family
        and entry.get("source_url") == survivor.get("source_url")
        and entry.get("status") == "ABSORBED"
        for entry in absorbed
    ):
        raise RegistrationBlocked("discovery_absorption_evidence_missing")
    if not isinstance(implemented, list) or not any(
        isinstance(entry, dict)
        and entry.get("candidate_id") == source_id
        and entry.get("family") == family
        and entry.get("source_url") == survivor.get("source_url")
        and entry.get("status") == "IMPLEMENTED"
        for entry in implemented
    ):
        raise RegistrationBlocked("implementation_absorption_evidence_missing")

    experiment_id = f"BC{bc}:REGISTRATION:{candidate_hash}"
    lineage = read_lineage()
    existing = next((entry for entry in lineage if entry.get("experiment_id") == experiment_id), None)
    if existing is not None:
        result = existing.get("result") or {}
        if (existing.get("verdict") != "REGISTERED"
                or result.get("candidate_hash") != candidate_hash
                or result.get("parent_failure_hash") != digest(failure)
                or result.get("novelty_key") != novelty
                or result.get("family") != family):
            raise RegistrationBlocked("existing_registration_lineage_mismatch")
        return {
            "bc": bc, "candidate": candidate, "failure": failure,
            "experiment_id": experiment_id, "created": False,
            "candidate_hash": candidate_hash, "checkpoint_seq": state["checkpoint_seq"],
        }

    evaluated_paths = [
        ROOT / f"research/bc{bc}_is_result.json",
        ROOT / f"research/bc{bc}_validation_result.json",
        ROOT / f"research/frozen_candidates/BC{bc}.json",
        ROOT / f"research/oos/BC{bc}_oos_result.json",
        ROOT / f"research/oos/BC{bc}_oos_result_receipt.json",
    ]
    if any(path.exists() for path in evaluated_paths):
        raise RegistrationBlocked("evaluation_artifact_exists_without_registration_lineage")

    data_hash = hashlib.sha256(DATA.read_bytes()).hexdigest() if DATA.exists() else parent_validation.get("dataset", {}).get("sha256")
    if not data_hash:
        raise RegistrationBlocked("data_lineage_hash_missing")
    return {
        "bc": bc, "candidate": candidate, "failure": failure,
        "parent_validation": parent_validation, "survivor": survivor,
        "experiment_id": experiment_id, "created": True,
        "candidate_hash": candidate_hash, "checkpoint_seq": state["checkpoint_seq"],
        "data_hash": data_hash, "novelty_key": novelty, "family": family,
    }


def register():
    validated = validate_queued_candidate()
    if validated is None:
        print("CANDIDATE_REGISTRATION_NO_ACTIVE_QUEUE")
        emit_outputs(ready=True, queued=False, created=False)
        return 0
    if not validated["created"]:
        print(f"CANDIDATE_REGISTRATION_LINEAGE_EXISTS experiment_id={validated['experiment_id']}")
        emit_outputs(ready=True, queued=True, created=False, bc=validated["bc"])
        return 0

    candidate = validated["candidate"]
    failure = validated["failure"]
    bc = validated["bc"]
    record = {
        "experiment_id": validated["experiment_id"],
        "generation": bc,
        "parent_artifacts": [
            f"research/failure_analysis/BC{bc - 1}.json",
            f"research/bc{bc - 1}_validation_result.json",
            "research/autonomous_candidates/BC%d.json" % bc,
            "research/bc_queue.json",
            "research/discovery/survivors.json",
            "research/discovery/.search_memory.json",
            "research/discovery/absorption_proof.json",
            "research/discovery/implementation_absorption_proof.json",
        ],
        "hypothesis": candidate.get("hypothesis_id", "UNKNOWN"),
        "change": candidate.get("conceptual_change", "UNKNOWN"),
        "code_revision": os.environ.get("GITHUB_SHA", "workflow-main"),
        "config_hash": validated["candidate_hash"],
        "data_hash": validated["data_hash"],
        "evaluator": "research.register_candidate_lineage + research.family_registry",
        "result": {
            "status": "REGISTERED_NOT_EVALUATED",
            "candidate_hash": validated["candidate_hash"],
            "parent_failure_hash": digest(failure),
            "novelty_key": validated["novelty_key"],
            "family": validated["family"],
            "checkpoint_seq": validated["checkpoint_seq"],
            "oos_selection_used": False,
        },
        "verdict": "REGISTERED",
        "decision": "REGISTERED_CANDIDATE",
        "evidence": [
            f"research/autonomous_candidates/BC{bc}.json",
            f"research/failure_analysis/BC{bc - 1}.json",
            f"research/bc{bc - 1}_validation_result.json",
            "research/discovery/survivors.json",
            "research/discovery/.search_memory.json",
            "research/discovery/absorption_proof.json",
            "research/discovery/implementation_absorption_proof.json",
        ] + list(candidate.get("evidence_sources", [])),
        "findings": [],
        "constraints": [
            "IS_THEN_VALIDATION_REQUIRED_BEFORE_OOS",
            "OOS_SELECTION_FORBIDDEN",
            "FROZEN_CANDIDATE_REQUIRED_BEFORE_FUTURE_OOS",
        ],
        "claims": [],
    }
    append_experiment(record)
    print(f"CANDIDATE_REGISTRATION_LINEAGE_CREATED experiment_id={validated['experiment_id']} candidate_hash={validated['candidate_hash']}")
    emit_outputs(ready=True, queued=True, created=True, bc=bc)
    return 0


def main() -> int:
    try:
        return register()
    except (RegistrationBlocked, OSError, json.JSONDecodeError, TypeError) as exc:
        print(f"CANDIDATE_REGISTRATION_BLOCKED reason={exc}")
        emit_outputs(ready=False, queued=False, created=False)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
