import copy
from research.bc_controller import append_promotion_event,migrate_legacy_state
from research.oos_lifecycle import OOSLifecycleError

def test_legacy_verdict_demoted():
 s={"history":[{"bc":306,"decision":"PROMOTE_TO_FUTURE_OOS_TEST","oos_verdict":"OOS_FAIL"}],"terminal":False,"terminal_reason":"OOS_FAIL"}
 assert migrate_legacy_state(s)
 e=s["history"][0]; assert e["oos_verdict"] is None and e["legacy_oos_verdict"]=="OOS_FAIL" and e["oos_state"]=="UNKNOWN"; assert s["terminal_reason"] is None

def test_nonpromotion_legacy_verdict_demoted():
 s={"history":[{"bc":307,"decision":"REJECT_BC","oos_verdict":"OOS_FAIL"}]}
 assert migrate_legacy_state(s); assert s["history"][0]["oos_verdict"] is None

def test_migration_idempotent():
 s={"history":[{"bc":306,"decision":"PROMOTE_TO_FUTURE_OOS_TEST","oos_verdict":"OOS_FAIL"}],"terminal":False,"terminal_reason":"OOS_FAIL"}
 migrate_legacy_state(s); snap=copy.deepcopy(s); assert migrate_legacy_state(s) is False; assert s==snap

def test_promotion_rebinding_fails_closed():
 s={"history":[]}; append_promotion_event(s,310,"a")
 try: append_promotion_event(s,310,"b")
 except OOSLifecycleError as e: assert str(e)=="PROMOTION_CANDIDATE_BINDING_MISMATCH"
 else: raise AssertionError("candidate rebinding accepted")

def test_malformed_history_fails_closed():
 try: migrate_legacy_state({"history":[1]})
 except OOSLifecycleError as e: assert str(e)=="STATE_HISTORY_ENTRY_INVALID"
 else: raise AssertionError("malformed history accepted")

import copy
from research.bc_controller import append_oos_event, append_promotion_event
from research.oos_lifecycle import OOSLifecycleError, lifecycle_event

def test_oos_event_exact_replay_is_idempotent():
    s={"history":[]}
    append_promotion_event(s, 306, "c306")
    e=lifecycle_event("OOS_AUTHORIZED", bc=306, candidate_hash="c306")
    first=append_oos_event(s,e)
    second=append_oos_event(s,copy.deepcopy(e))
    assert first == second
    assert len([x for x in s["history"] if x.get("oos_state")=="OOS_AUTHORIZED"]) == 1

def test_oos_event_same_state_with_changed_evidence_fails_closed():
    s={"history":[]}
    append_promotion_event(s, 306, "c306")
    e=lifecycle_event("OOS_AUTHORIZED", bc=306, candidate_hash="c306")
    append_oos_event(s,e)
    bad=copy.deepcopy(e); bad["attempt_id"]="tampered"
    try:
        append_oos_event(s,bad)
    except OOSLifecycleError as exc:
        assert str(exc) in {"OOS_EVENT_REPLAY_MISMATCH","DUPLICATE_OOS_STATE"}
    else:
        raise AssertionError("tampered replay accepted")
