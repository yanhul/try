import sqlite3
import pytest
from engine.aios_worker_runtime import WorkerJobStore, WorkerQueueError

def store_for(tmp_path):
    calls=[]
    def verify(contract, permit):
        calls.append((contract,permit))
        return contract == "contract-1" and permit == "permit-1"
    return WorkerJobStore(tmp_path/"jobs.sqlite",verify),calls

def enqueue(store, task="task-1", key="idem-1"):
    store.enqueue(task_id=task,idempotency_key=key,contract_id="contract-1",
                  permit_id="permit-1",payload={"input_digest":"sha256:abc"})

def test_claim_heartbeat_checkpoint_and_observation(tmp_path):
    store,calls=store_for(tmp_path); enqueue(store)
    job=store.claim(worker_id="worker-a",lease_seconds=60)
    assert job["status"]=="CLAIMED"
    store.heartbeat(task_id="task-1",worker_id="worker-a",lease_seconds=60)
    store.checkpoint(task_id="task-1",worker_id="worker-a",checkpoint=2)
    with pytest.raises(WorkerQueueError):
        store.checkpoint(task_id="task-1",worker_id="worker-a",checkpoint=1)
    store.observe(task_id="task-1",worker_id="worker-a",evidence_ref="artifact://result")
    assert store.get("task-1")["status"]=="OBSERVED" and calls

def test_enqueue_requires_aios_authority(tmp_path):
    store,_=store_for(tmp_path)
    with pytest.raises(PermissionError):
        store.enqueue(task_id="t",idempotency_key="i",contract_id="wrong",
                      permit_id="permit-1",payload={})

def test_duplicate_idempotency_and_unknown_are_not_retried(tmp_path):
    store,_=store_for(tmp_path); enqueue(store)
    with pytest.raises(sqlite3.IntegrityError):
        enqueue(store,"task-2","idem-1")
    store.claim(worker_id="worker-a",lease_seconds=60)
    store.mark_unknown(task_id="task-1",worker_id="worker-a",reason="provider_timeout")
    assert store.claim(worker_id="worker-b",lease_seconds=60) is None
    assert store.get("task-1")["status"]=="UNKNOWN"

def test_observed_requires_evidence_and_live_owner(tmp_path):
    store,_=store_for(tmp_path); enqueue(store)
    store.claim(worker_id="worker-a",lease_seconds=60)
    with pytest.raises(ValueError):
        store.observe(task_id="task-1",worker_id="worker-a",evidence_ref="")
    with pytest.raises(WorkerQueueError):
        store.observe(task_id="task-1",worker_id="worker-b",evidence_ref="artifact://x")

def test_expired_lease_becomes_unknown_and_is_not_reclaimed(tmp_path, monkeypatch):
    import engine.aios_worker_runtime as runtime
    clock = [1000.0]
    monkeypatch.setattr(runtime.time, "time", lambda: clock[0])
    store,_=store_for(tmp_path); enqueue(store)
    assert store.claim(worker_id="worker-a",lease_seconds=10)["status"]=="CLAIMED"
    clock[0] = 1011.0
    assert store.claim(worker_id="worker-b",lease_seconds=10) is None
    job=store.get("task-1")
    assert job["status"]=="UNKNOWN"
    assert job["block_reason"]=="lease_expired_ambiguous"

def test_worker_payload_rejects_plaintext_secrets_but_allows_references(tmp_path):
    store,_=store_for(tmp_path)
    with pytest.raises(ValueError, match="must reference secrets"):
        store.enqueue(task_id="t-secret",idempotency_key="i-secret",
                      contract_id="contract-1",permit_id="permit-1",
                      payload={"provider":{"api_key":"plaintext"}})
    store.enqueue(task_id="t-ref",idempotency_key="i-ref",
                  contract_id="contract-1",permit_id="permit-1",
                  payload={"provider":{"api_key_ref":"secret-manager://gemini"}})
    assert store.get("t-ref")["status"]=="QUEUED"
