import pytest

from research.continuation_reconciliation import (
    ReconciliationBlocked,
    validate_artifacts,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


def artifacts(*, intent_hash=HASH_A, intent_checkpoint=13794,
              state_checkpoint=13794, candidate_hash=HASH_A,
              queue_hash=HASH_A, registrations=None):
    state = {
        "campaign_id": "BTCUSDT-1H-AUTONOMOUS-002",
        "current_bc": 477,
        "next_bc": 477,
        "checkpoint_seq": state_checkpoint,
    }
    intent = {
        "campaign_id": state["campaign_id"],
        "current_bc": 477,
        "next_bc": 477,
        "checkpoint_seq": intent_checkpoint,
        "authorized_candidate_hash": intent_hash,
    }
    candidate = {"bc": 477, "candidate_hash": candidate_hash}
    queue = [{"bc": 477, "candidate_hash": queue_hash}]
    if registrations is None:
        registrations = [{
            "experiment_id": f"BC477:REGISTRATION:{candidate_hash}",
            "generation": 477,
            "verdict": "REGISTERED",
            "result": {
                "candidate_hash": candidate_hash,
                "checkpoint_seq": state_checkpoint,
            },
        }]
    return state, intent, queue, candidate, registrations


def run(data, status="PENDING"):
    validate_artifacts(
        state=data[0], intent=data[1], queue=data[2],
        candidate=data[3], lineage=data[4], status=status,
    )


def test_exact_durable_authorization_passes():
    run(artifacts())


def test_real_bc477_shape_fails_closed_on_ten_conflicting_registrations():
    hashes = [f"{i:064x}" for i in range(1, 11)]
    registrations = [{
        "experiment_id": f"BC477:REGISTRATION:{value}",
        "generation": 477,
        "verdict": "REGISTERED",
        "result": {"candidate_hash": value, "checkpoint_seq": 13767 + 3 * i},
    } for i, value in enumerate(hashes)]
    data = artifacts(
        intent_hash=HASH_A,
        intent_checkpoint=13794,
        state_checkpoint=13809,
        candidate_hash=HASH_B,
        queue_hash=HASH_B,
        registrations=registrations,
    )
    with pytest.raises(ReconciliationBlocked, match="conflicting_candidate_registrations_for_bc_477:10"):
        run(data)


def test_pending_intent_hash_must_match_candidate_even_if_queue_matches():
    data = artifacts(intent_hash=HASH_A, candidate_hash=HASH_B, queue_hash=HASH_B)
    with pytest.raises(ReconciliationBlocked, match="pending_intent_candidate_hash_mismatch"):
        run(data)


def test_pending_checkpoint_must_match_exactly():
    data = artifacts(intent_checkpoint=13794, state_checkpoint=13809)
    with pytest.raises(ReconciliationBlocked, match="pending_intent_checkpoint_mismatch"):
        run(data)


def test_stale_intent_can_only_be_reissued_from_unique_current_registration():
    data = artifacts(intent_hash=HASH_B, intent_checkpoint=13794, state_checkpoint=13809)
    # A stale continuation is acceptable only when the new candidate has one
    # registration tied to the current checkpoint; caller verifies the source receipt.
    run(data, status="STALE")


def test_stale_intent_still_rejects_conflicting_candidate_history():
    data = artifacts(
        intent_hash=HASH_B, intent_checkpoint=13794, state_checkpoint=13809,
        registrations=[
            {"generation": 477, "verdict": "REGISTERED",
             "result": {"candidate_hash": HASH_A, "checkpoint_seq": 13809}},
            {"generation": 477, "verdict": "REGISTERED",
             "result": {"candidate_hash": HASH_B, "checkpoint_seq": 13809}},
        ],
    )
    with pytest.raises(ReconciliationBlocked, match="conflicting_candidate_registrations_for_bc_477:2"):
        run(data, status="STALE")
