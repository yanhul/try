"""Failure-oriented tests for TRY's AIOS durable scheduler adapter."""
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from engine.aios_durable_runtime import DurableQueueError, TrySQLiteDurableRuntime


class Clock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def dispatched(effect_id="EF-1", attempt=1):
    return {
        "effect_id": effect_id,
        "attempt_id": f"{effect_id}:attempt:{attempt}",
        "attempt": attempt,
        "provider": "fixture-provider",
        "state": "DISPATCHED",
    }


class TryDurableRuntimeTests(unittest.TestCase):
    def make_runtime(self, root, clock=None):
        return TrySQLiteDurableRuntime(
            Path(root) / "runtime.sqlite3",
            provider_name="fixture-provider",
            lease_seconds=10,
            clock=clock or Clock(),
        )

    def test_submit_is_idempotent_and_bound_to_effect_attempt_provider(self):
        with TemporaryDirectory() as root:
            runtime = self.make_runtime(root)
            effect = dispatched()
            first = runtime.submit(effect=effect, attempt_id=effect["attempt_id"])
            second = runtime.submit(effect=effect, attempt_id=effect["attempt_id"])
            self.assertEqual(first, second)
            self.assertEqual(runtime.claim(worker_id="worker-a")["effect_id"], "EF-1")
            with self.assertRaises(DurableQueueError):
                runtime.submit(effect={**effect, "provider": "other"}, attempt_id=effect["attempt_id"])

    def test_two_workers_cannot_claim_same_handoff(self):
        with TemporaryDirectory() as root:
            runtime = self.make_runtime(root)
            effect = dispatched()
            runtime.submit(effect=effect, attempt_id=effect["attempt_id"])
            with ThreadPoolExecutor(max_workers=2) as pool:
                claims = list(pool.map(
                    lambda worker: runtime.claim(worker_id=worker),
                    ("worker-a", "worker-b"),
                ))
            self.assertEqual(sum(claim is not None for claim in claims), 1)

    def test_heartbeat_extends_only_current_workers_live_lease(self):
        with TemporaryDirectory() as root:
            clock = Clock()
            runtime = self.make_runtime(root, clock)
            effect = dispatched()
            runtime.submit(effect=effect, attempt_id=effect["attempt_id"])
            runtime.claim(worker_id="worker-a")
            self.assertEqual(runtime.heartbeat(
                effect_id="EF-1", attempt_id=effect["attempt_id"], worker_id="worker-a"
            ), 1010.0)
            with self.assertRaises(DurableQueueError):
                runtime.heartbeat(
                    effect_id="EF-1", attempt_id=effect["attempt_id"], worker_id="worker-b"
                )

    def test_expired_lease_becomes_unknown_and_is_not_requeued(self):
        with TemporaryDirectory() as root:
            clock = Clock()
            runtime = self.make_runtime(root, clock)
            effect = dispatched()
            runtime.submit(effect=effect, attempt_id=effect["attempt_id"])
            runtime.claim(worker_id="worker-a")
            clock.advance(11)
            self.assertEqual(runtime.recover_expired_leases(), [("EF-1", effect["attempt_id"])])
            self.assertIsNone(runtime.claim(worker_id="worker-b"))
            with self.assertRaises(DurableQueueError):
                runtime.heartbeat(
                    effect_id="EF-1", attempt_id=effect["attempt_id"], worker_id="worker-a"
                )

    def test_resume_requires_existing_exact_handoff(self):
        with TemporaryDirectory() as root:
            runtime = self.make_runtime(root)
            effect = dispatched()
            with self.assertRaises(DurableQueueError):
                runtime.resume(effect=effect, attempt_id=effect["attempt_id"])
            runtime.submit(effect=effect, attempt_id=effect["attempt_id"])
            self.assertEqual(
                runtime.resume(effect=effect, attempt_id=effect["attempt_id"]).attempt_id,
                effect["attempt_id"],
            )

    def test_resume_refuses_claimed_handoff_to_prevent_ambiguous_reexecution(self):
        with TemporaryDirectory() as root:
            runtime = self.make_runtime(root)
            effect = dispatched()
            runtime.submit(effect=effect, attempt_id=effect["attempt_id"])
            runtime.claim(worker_id="worker-a")
            with self.assertRaises(DurableQueueError):
                runtime.resume(effect=effect, attempt_id=effect["attempt_id"])

    def test_retry_requires_new_aios_attempt_identity(self):
        with TemporaryDirectory() as root:
            runtime = self.make_runtime(root)
            effect = dispatched(attempt=2)
            with self.assertRaises(ValueError):
                runtime.retry(effect=effect, attempt_id=effect["attempt_id"], attempt=1)

    def test_caller_supplied_state_string_cannot_promote_terminal(self):
        with TemporaryDirectory() as root:
            runtime = self.make_runtime(root)
            self.assertFalse(hasattr(runtime, "mark_aios_terminal"))
            effect = dispatched()
            runtime.submit(effect=effect, attempt_id=effect["attempt_id"])
            runtime.claim(worker_id="worker-a")
            # No AIOS store holds this effect: verification must fail closed.
            aios = Path(root) / "aios"
            aios.mkdir()
            from engine.aios_authority_reader import AuthorityRejected
            with self.assertRaises(AuthorityRejected):
                runtime.mirror_verified_terminal(
                    aios_dir=str(aios), effect_id="EF-1", attempt_id=effect["attempt_id"],
                    worker_id="worker-a")
            self.assertEqual(
                runtime.get_handoff(effect_id="EF-1", attempt_id=effect["attempt_id"])["status"],
                "CLAIMED")

    def test_retry_gated_until_previous_attempt_unknown(self):
        with TemporaryDirectory() as root:
            clock = Clock()
            runtime = self.make_runtime(root, clock)
            first = dispatched(attempt=1)
            second = dispatched(attempt=2)
            with self.assertRaises(DurableQueueError):  # no previous attempt row
                runtime.retry(effect=second, attempt_id=second["attempt_id"], attempt=2)
            runtime.submit(effect=first, attempt_id=first["attempt_id"])
            with self.assertRaises(DurableQueueError):  # previous still SUBMITTED
                runtime.retry(effect=second, attempt_id=second["attempt_id"], attempt=2)
            runtime.claim(worker_id="worker-a")
            self.assertFalse(runtime.can_retry(effect_id="EF-1", attempt=2))  # live lease
            clock.advance(11)
            runtime.recover_expired_leases()
            self.assertTrue(runtime.can_retry(effect_id="EF-1", attempt=2))
            self.assertEqual(
                runtime.retry(effect=second, attempt_id=second["attempt_id"], attempt=2).attempt_id,
                second["attempt_id"])

    def test_schema_migrates_previous_slice_database(self):
        import sqlite3
        with TemporaryDirectory() as root:
            db = Path(root) / "runtime.sqlite3"
            conn = sqlite3.connect(db)
            conn.execute("""CREATE TABLE runtime_handoffs (effect_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL, provider TEXT NOT NULL, payload_json TEXT NOT NULL,
                status TEXT NOT NULL, worker_id TEXT, lease_expires_at REAL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                PRIMARY KEY(effect_id, attempt_id))""")
            conn.commit()
            conn.close()
            runtime = self.make_runtime(root)
            effect = dispatched()
            runtime.submit(effect=effect, attempt_id=effect["attempt_id"])
            row = runtime.get_handoff(effect_id="EF-1", attempt_id=effect["attempt_id"])
            self.assertIn("aios_receipt_json", row)
            self.assertIn("unknown_reason", row)


if __name__ == "__main__":
    unittest.main()
