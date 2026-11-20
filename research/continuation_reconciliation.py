"""Fail-closed consistency gate for durable continuation authorization.

This module validates the durable artifacts before a continuation intent can be
reissued or a controller can be dispatched. It never repairs or rewrites state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReconciliationBlocked(ValueError):
    pass


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationBlocked(f"artifact_unreadable:{path.relative_to(ROOT)}") from exc


def _registered_bc(entry: dict) -> int | None:
    generation = entry.get("generation")
    if isinstance(generation, int):
        return generation
    experiment_id = str(entry.get("experiment_id") or "")
    prefix = "BC"
    marker = ":REGISTRATION:"
    if experiment_id.startswith(prefix) and marker in experiment_id:
        try:
            return int(experiment_id.split(":", 1)[0][len(prefix):])
        except ValueError:
            return None
    return None


def validate_artifacts(*, state: dict, intent: dict, queue: list,
                        candidate: dict, lineage: list, status: str) -> None:
    """Validate one queued BC against checkpoint, authorization and immutable lineage."""
    if not isinstance(state, dict) or not isinstance(intent, dict):
        raise ReconciliationBlocked("state_or_intent_not_object")
    if not isinstance(queue, list) or not isinstance(lineage, list):
        raise ReconciliationBlocked("queue_or_lineage_not_list")
    if not queue:
        return

    bc = state.get("next_bc")
    if not isinstance(bc, int) or state.get("current_bc") != bc:
        raise ReconciliationBlocked("current_next_bc_mismatch")
    if state.get("campaign_id") != intent.get("campaign_id"):
        raise ReconciliationBlocked("campaign_id_mismatch")
    if candidate.get("bc") != bc:
        raise ReconciliationBlocked("candidate_bc_mismatch")

    matches = [item for item in queue if isinstance(item, dict) and item.get("bc") == bc]
    if len(matches) != 1:
        raise ReconciliationBlocked("queue_entry_missing_or_ambiguous")
    candidate_hash = candidate.get("candidate_hash")
    if not isinstance(candidate_hash, str) or not candidate_hash:
        raise ReconciliationBlocked("candidate_hash_missing")
    if matches[0].get("candidate_hash") != candidate_hash:
        raise ReconciliationBlocked("queue_candidate_hash_mismatch")

    registrations = [
        entry for entry in lineage
        if isinstance(entry, dict)
        and entry.get("verdict") == "REGISTERED"
        and _registered_bc(entry) == bc
    ]
    registered_hashes = {
        (entry.get("result") or {}).get("candidate_hash")
        for entry in registrations
        if isinstance(entry.get("result"), dict)
        and (entry.get("result") or {}).get("candidate_hash")
    }
    if len(registered_hashes) > 1:
        raise ReconciliationBlocked(
            f"conflicting_candidate_registrations_for_bc_{bc}:{len(registered_hashes)}"
        )
    if registered_hashes != {candidate_hash}:
        raise ReconciliationBlocked("candidate_not_bound_to_unique_registration_lineage")
    if not registrations:
        raise ReconciliationBlocked("candidate_registration_lineage_missing")
    registration_checkpoints = {
        (entry.get("result") or {}).get("checkpoint_seq")
        for entry in registrations
    }
    if registration_checkpoints != {state.get("checkpoint_seq")}:
        raise ReconciliationBlocked("registration_checkpoint_not_current")

    if status == "PENDING":
        if intent.get("checkpoint_seq") != state.get("checkpoint_seq"):
            raise ReconciliationBlocked("pending_intent_checkpoint_mismatch")
        if intent.get("current_bc") != state.get("current_bc") or intent.get("next_bc") != state.get("next_bc"):
            raise ReconciliationBlocked("pending_intent_bc_mismatch")
        if intent.get("authorized_candidate_hash") != candidate_hash:
            raise ReconciliationBlocked("pending_intent_candidate_hash_mismatch")
    elif status == "STALE":
        # A completed, independently verified controller receipt may authorize a
        # fresh intent only when the new candidate has a unique registration at
        # the exact current checkpoint. The caller verifies the source run receipt.
        pass
    else:
        raise ReconciliationBlocked(f"unsupported_continuation_status:{status}")


def validate_repository(root: Path = ROOT, *, status: str) -> None:
    state = _load(root / "research/bc_lifecycle_state.json")
    intent = _load(root / "research/continuation_intent.json")
    queue = _load(root / "research/bc_queue.json")
    if not queue:
        return
    bc = state.get("next_bc") if isinstance(state, dict) else None
    if not isinstance(bc, int):
        raise ReconciliationBlocked("next_bc_invalid")
    candidate = _load(root / f"research/autonomous_candidates/BC{bc}.json")
    lineage_path = root / "research/lineage.jsonl"
    try:
        lineage = [
            json.loads(line) for line in lineage_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationBlocked("lineage_unreadable") from exc
    validate_artifacts(
        state=state, intent=intent, queue=queue, candidate=candidate,
        lineage=lineage, status=status,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", required=True, choices=("PENDING", "STALE"))
    args = parser.parse_args()
    try:
        validate_repository(status=args.status)
    except ReconciliationBlocked as exc:
        print(f"CONTINUATION_RECONCILIATION_BLOCKED reason={exc}")
        return 2
    print(f"CONTINUATION_RECONCILIATION_VERIFIED status={args.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
