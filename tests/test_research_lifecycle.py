import pytest
from research.lifecycle import LifecycleEvent, LifecycleStore, new_attempt_id

def event(candidate, work, current, target, reason, attempt=None):
    return LifecycleEvent("camp",candidate,work,attempt,current,target,reason)

def test_lifecycle_is_durable_and_ordered(tmp_path):
    store=LifecycleStore(tmp_path/"lifecycle.jsonl")
    cid="candidate-1"; work="work-1"
    store.ensure_discovered("camp",cid,work)
    store.transition(event(cid,work,"DISCOVERED","CLAIMED","CLAIM"))
    attempt=new_attempt_id(cid,1)
    store.transition(event(cid,work,"CLAIMED","EVALUATING","EXECUTE",attempt))
    store.transition(event(cid,work,"EVALUATING","VALIDATING","RECEIPT",attempt))
    store.transition(event(cid,work,"VALIDATING","REJECTED","OOS_OR_GATE_REJECT"))
    assert store.current(cid)=="REJECTED"
    assert len(store.read())==5

def test_invalid_transition_fails_closed(tmp_path):
    store=LifecycleStore(tmp_path/"lifecycle.jsonl"); cid="candidate-2"; work="work-2"
    store.ensure_discovered("camp",cid,work)
    with pytest.raises(ValueError,match="invalid_lifecycle_transition"):
        store.transition(event(cid,work,"DISCOVERED","OOS_EXECUTING","BYPASS"))

def test_state_conflict_fails_closed(tmp_path):
    store=LifecycleStore(tmp_path/"lifecycle.jsonl"); cid="candidate-3"; work="work-3"
    store.ensure_discovered("camp",cid,work)
    with pytest.raises(ValueError,match="lifecycle_state_conflict"):
        store.transition(event(cid,work,"CLAIMED","TRANSLATING","STALE"))

def test_unknown_can_reconcile_without_unknown_dispatch(tmp_path):
    store=LifecycleStore(tmp_path/"lifecycle.jsonl"); cid="candidate-4"; work="work-4"
    store.ensure_discovered("camp",cid,work)
    store.transition(event(cid,work,"DISCOVERED","CLAIMED","CLAIM"))
    store.transition(event(cid,work,"CLAIMED","EVALUATING","EXECUTE"))
    store.transition(event(cid,work,"EVALUATING","UNKNOWN","CRASH_OR_TIMEOUT"))
    with pytest.raises(ValueError):
        store.transition(event(cid,work,"UNKNOWN","PROMOTED","ILLEGAL_DIRECT_PROMOTION"))
    store.transition(event(cid,work,"UNKNOWN","EVALUATING","RECONCILED_RETRY"))
    assert store.current(cid)=="EVALUATING"
