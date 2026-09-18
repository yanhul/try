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
