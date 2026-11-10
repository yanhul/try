"""Adversarial tests: AIOS execution claim at the worker boundary and
AIOS-dispatch / SQLite-enqueue crash recovery.

Real pinned AIOS file store + real TrySQLiteDurableRuntime. The crash tests
kill a real child process with ``os._exit`` at the injected boundary. Cross-
process exclusion itself is proven in AIOS (tests/test_effect_execution_claim.py);
these tests prove TRY routes every path through it.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import unittest
from tempfile import TemporaryDirectory
from unittest import mock

try:
    from tests.test_aios_durable_runtime_worker import (ACTOR, PROVIDER, REPO_ROOT, AIOS_ROOT, Env,
                                                        LedgerProvider, side_effects)
except ImportError:  # unittest discover -s tests (CI)
    from test_aios_durable_runtime_worker import (ACTOR, PROVIDER, REPO_ROOT, AIOS_ROOT, Env,
                                                  LedgerProvider, side_effects)
import core.effect_authority as _ea
from core.effect_authority import create_effect, unknown
from core.mutation import canonical_json, _digest_bytes, _write_staged
from core.runtime import execute_attempt
from core.authority import load_contract

from engine import aios_durable_worker as worker_mod
from engine.aios_durable_runtime import DurableQueueError
from engine.aios_durable_worker import enqueue_dispatched, enqueue_retry

# getattr so these tests run (and fail on behaviour) against the pre-fix code.
HandoffPending = getattr(worker_mod, "HandoffPending", DurableQueueError)
reconcile_handoffs = getattr(worker_mod, "reconcile_handoffs", lambda *a, **k: {})
claim_execution = getattr(_ea, "claim_execution", None)


def rows(env):
    with sqlite3.connect(env.db) as conn:
        return conn.execute("SELECT effect_id,attempt_id,status FROM runtime_handoffs "
                            "ORDER BY attempt_id").fetchall()


def crash_child(env, op, boundary):
    """Run enqueue_dispatched in a child process that hard-exits at ``boundary``."""
    script = textwrap.dedent(f"""
        import os, sys
        sys.path[:0] = [{str(REPO_ROOT)!r}, {str(AIOS_ROOT)!r}]
        import engine.aios_durable_worker as w
        import core.effect_authority as ea
        from engine.aios_durable_runtime import TrySQLiteDurableRuntime
        rt = TrySQLiteDurableRuntime({str(env.db)!r}, provider_name={PROVIDER!r})
        boundary = {boundary!r}
        if boundary == "after_create":
            w.dispatch = lambda *a, **k: os._exit(9)
        elif boundary == "after_dispatch":
            rt.submit = lambda **k: os._exit(9)
        elif boundary == "after_sqlite_insert":
            real = rt.submit
            def submit(**k):
                real(**k); os._exit(9)
            rt.submit = submit
        w.enqueue_dispatched({str(env.aios)!r}, {env.contract_id!r}, {env.permit_id!r},
                             {op!r}, {ACTOR!r}, rt)
        os._exit(0)
    """)
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 9, proc.stderr


class ExecutionClaimAtWorkerBoundary(unittest.TestCase):
    def test_unknown_after_validation_before_provider_call_blocks_execution(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eff = env.enqueue()
            real_hb = env.runtime.heartbeat

            def racing_heartbeat(**kw):  # after authoritative_dispatch, before execute_attempt
                unknown(str(env.aios), eff["effect_id"], ACTOR, "competing process: ambiguity")
                return real_hb(**kw)

            with mock.patch.object(env.runtime, "heartbeat", side_effect=racing_heartbeat):
                res = env.worker().run_once()
            self.assertEqual(side_effects(env.ledger), 0)
            self.assertFalse(res.execution_attempted)
            self.assertEqual(res.queue_status, "UNKNOWN")
            self.assertEqual(env.aios_effect(eff["effect_id"])["state"], "UNKNOWN")

    def test_concurrent_executor_same_attempt_only_one_provider_call(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eff = env.enqueue()
            real_hb = env.runtime.heartbeat
            rogue = LedgerProvider(env.ledger)

            def rogue_first(**kw):  # another executor wins the AIOS claim for this attempt
                contract = load_contract(str(env.aios), env.contract_id)
                execute_attempt(str(env.aios), contract, dict(eff), ACTOR, rogue, eff["attempt_id"])
                return real_hb(**kw)

            with mock.patch.object(env.runtime, "heartbeat", side_effect=rogue_first):
                res = env.worker().run_once()
            self.assertEqual(side_effects(env.ledger), 1)
            self.assertFalse(res.execution_attempted)
            self.assertEqual(res.queue_status, "OBSERVED_SUCCESS")  # mirrored verified receipt


class HandoffCrashRecovery(unittest.TestCase):
    def test_crash_after_create_before_dispatch_is_safely_replayable(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            crash_child(env, "op-c1", "after_create")
            self.assertEqual(rows(env), [])
            self.assertEqual(reconcile_handoffs(env.aios, env.runtime), {})  # PLANNED: nothing
            eff = env.enqueue("op-c1")  # replay the enqueue
            self.assertEqual(env.worker().run_once().queue_status, "OBSERVED_SUCCESS")
            self.assertEqual(side_effects(env.ledger), 1)
            self.assertEqual(env.aios_effect(eff["effect_id"])["state"], "OBSERVED_SUCCESS")

    def test_crash_after_aios_dispatch_before_sqlite_enqueue_recovers_once(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            crash_child(env, "op-c2", "after_dispatch")
            self.assertEqual(rows(env), [])
            (eid, rec), = [(k, v) for k, v in __import__("core.external_effect", fromlist=["x"])
                           .load_effects(str(env.aios)).items()]
            self.assertEqual(rec["state"], "DISPATCHED")
            key = (eid, f"{eid}:attempt:1")
            for _ in range(3):  # idempotent
                out = reconcile_handoffs(env.aios, env.runtime)
            self.assertEqual(out, {key: "present"})
            self.assertEqual(len(rows(env)), 1)
            self.assertEqual(side_effects(env.ledger), 0)  # reconciliation never executes
            self.assertEqual(env.worker().run_once().queue_status, "OBSERVED_SUCCESS")
            self.assertIsNone(env.worker().run_once())
            reconcile_handoffs(env.aios, env.runtime)
            self.assertEqual(side_effects(env.ledger), 1)

    def test_crash_after_sqlite_insert_needs_no_recovery(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            crash_child(env, "op-c3", "after_sqlite_insert")
            self.assertEqual(list(reconcile_handoffs(env.aios, env.runtime).values()), ["present"])
            env.worker().run_once()
            self.assertEqual(side_effects(env.ledger), 1)

    def test_sqlite_submit_failure_after_dispatch_is_recovered(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            with mock.patch.object(env.runtime, "submit",
                                   side_effect=sqlite3.OperationalError("disk I/O error")):
                with self.assertRaises(Exception) as cm:
                    env.enqueue("op-f")
            self.assertIsInstance(cm.exception, HandoffPending)
            self.assertEqual(rows(env), [])
            out = reconcile_handoffs(env.aios, env.runtime)
            self.assertEqual(list(out.values()), ["adopted"])
            env.worker().run_once()
            self.assertEqual(side_effects(env.ledger), 1)

    def test_claimed_dispatch_without_handoff_is_never_rescheduled(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            with mock.patch.object(env.runtime, "submit", side_effect=OSError("crash")):
                with self.assertRaises(Exception):
                    eff = env.enqueue("op-x")
            from core.external_effect import load_effects
            (eid, rec), = load_effects(str(env.aios)).items()
            # Some executor claimed (and may have called the provider) then died.
            claim_execution(str(env.aios), eid, rec["attempt_id"], PROVIDER, ACTOR, "dead-executor")
            for _ in range(2):
                out = reconcile_handoffs(env.aios, env.runtime)
            self.assertTrue(out[(eid, rec["attempt_id"])].startswith("claimed"))
            self.assertEqual(rows(env), [])
            self.assertIsNone(env.worker().run_once())
            self.assertEqual(side_effects(env.ledger), 0)


class RetryRaces(unittest.TestCase):
    def _unknown_attempt1(self, env):
        eff = env.enqueue("op-r")
        env.worker(LedgerProvider(env.ledger, fail=True)).run_once()  # provider timeout => UNKNOWN
        self.assertEqual(env.aios_effect(eff["effect_id"])["state"], "UNKNOWN")
        self.assertEqual(env.row(eff["effect_id"])["status"], "UNKNOWN")
        return eff["effect_id"]

    def test_concurrent_retry_only_one_consumes_attempt(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp, max_attempts=3)
            eid = self._unknown_attempt1(env)
            enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 2, env.runtime)
            with self.assertRaises((RuntimeError, DurableQueueError)):
                enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 2, env.runtime)
            self.assertEqual(env.aios_effect(eid)["attempt"], 2)
            self.assertEqual(len(rows(env)), 2)

    def test_retry_sqlite_reject_after_aios_retry_dispatch_is_recovered(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp, max_attempts=3)
            eid = self._unknown_attempt1(env)
            before = side_effects(env.ledger)
            with mock.patch.object(env.runtime, "retry",
                                   side_effect=DurableQueueError("retry gated: concurrent change")):
                with self.assertRaises(DurableQueueError):
                    enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 2, env.runtime)
            self.assertEqual(env.aios_effect(eid)["state"], "DISPATCHED")
            self.assertIsNone(env.row(eid, 2))
            self.assertEqual(reconcile_handoffs(env.aios, env.runtime)[(eid, f"{eid}:attempt:2")], "adopted")
            reconcile_handoffs(env.aios, env.runtime)
            self.assertEqual(env.worker().run_once().queue_status, "OBSERVED_SUCCESS")
            self.assertEqual(side_effects(env.ledger), before + 1)

    def test_recovered_retry_waits_for_scheduler_gate(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp, max_attempts=3)
            eid = self._unknown_attempt1(env)
            # Concurrent state change: attempt-1 row looks live (CLAIMED) in SQLite.
            with sqlite3.connect(env.db) as conn:
                conn.execute("UPDATE runtime_handoffs SET status='CLAIMED',worker_id='w-live',"
                             "lease_expires_at=? WHERE attempt_id=?",
                             (env.clock() + 30, f"{eid}:attempt:1"))
            with self.assertRaises(DurableQueueError):
                enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 2, env.runtime)
            # can_retry refused before AIOS retry_dispatch: no AIOS attempt consumed.
            self.assertEqual(env.aios_effect(eid)["state"], "UNKNOWN")
            # Force the split: AIOS consumes attempt 2 while SQLite still gates.
            from core.effect_authority import retry_dispatch
            retry_dispatch(str(env.aios), eid, ACTOR, f"{eid}:attempt:2", PROVIDER, 2,
                           handoff_runtime=env.runtime.name)
            key = (eid, f"{eid}:attempt:2")
            self.assertTrue(reconcile_handoffs(env.aios, env.runtime)[key].startswith("deferred"))
            self.assertIsNone(env.worker().run_once())
            env.clock.advance(31)
            env.runtime.recover_expired_leases()  # attempt-1 lease -> UNKNOWN (never requeued)
            self.assertEqual(reconcile_handoffs(env.aios, env.runtime)[key], "adopted")
            env.worker().run_once()
            self.assertEqual(env.aios_effect(eid)["state"], "OBSERVED_SUCCESS")


class JournalRecoveryBeforeReconcile(unittest.TestCase):
    def test_reconcile_rolls_forward_aios_dispatch_journal_before_scanning(self):
        """A crash after journal fsync but before effect rename must be recoverable."""
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            planned = create_effect(str(env.aios), env.contract_id, "op-journal", ACTOR,
                                    env.permit_id, "external_effect")
            eid = planned["effect_id"]
            attempt_id = f"{eid}:attempt:1"
            dispatched = dict(planned, state="DISPATCHED", attempt=1,
                              attempt_id=attempt_id, provider=PROVIDER,
                              handoff_runtime=env.runtime.name)
            event = {"kind": "external_effect", "action": "dispatch", "effect_id": eid,
                     "from_state": "PLANNED", "to_state": "DISPATCHED", "actor": ACTOR,
                     "attempt": 1, "attempt_id": attempt_id, "provider": PROVIDER,
                     "handoff_runtime": env.runtime.name}

            # Recreate the exact staged write-ahead journal left by commit_batch
            # after the journal is fsynced but before either atomic rename.
            staging = os.path.join(str(env.aios), ".staging", "batch-crash-before-rename")
            os.makedirs(staging, exist_ok=True)
            ops = []
            payloads = [
                (os.path.join("effects", eid + ".json"), dispatched),
                (os.path.join("events", f"effect-{eid}-DISPATCHED-attempt-1.json"), event),
            ]
            for index, (relative, payload) in enumerate(payloads):
                data = canonical_json(payload).encode("utf-8") + bytes([10])
                temporary = os.path.join(staging, f"{index}.tmp")
                destination = os.path.join(str(env.aios), relative)
                _write_staged(temporary, data)
                ops.append({"tmp": temporary, "dest": destination, "digest": _digest_bytes(data)})
            journal = {"batch_id": "batch-crash-before-rename", "ops": ops}
            _write_staged(os.path.join(staging, "journal.json"),
                          canonical_json(journal).encode("utf-8"))

            # The on-disk effect is still PLANNED and there is no SQLite row.
            self.assertEqual(env.aios_effect(eid)["state"], "PLANNED")
            self.assertEqual(rows(env), [])
            out = reconcile_handoffs(env.aios, env.runtime)
            self.assertEqual(out, {(eid, attempt_id): "adopted"})
            self.assertEqual(env.aios_effect(eid)["state"], "DISPATCHED")
            self.assertIsNotNone(env.row(eid))
            self.assertEqual(side_effects(env.ledger), 0)
            self.assertEqual(env.worker().run_once().queue_status, "OBSERVED_SUCCESS")
            self.assertEqual(side_effects(env.ledger), 1)


if __name__ == "__main__":
    unittest.main()
