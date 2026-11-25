import asyncio
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Installs the CPython Worker API doubles used by the existing conformance suite.
import test_entry
import algorithm_entry


class FakeStorage:
    def __init__(self):
        self.values = {}
        self.writes = []

    async def get(self, key):
        return self.values.get(key)

    async def put(self, key, value):
        self.writes.append(key)
        self.values[key] = value


class FakeContext:
    def __init__(self):
        self.storage = FakeStorage()


class AlgorithmEnv(test_entry._Env):
    TRY_ALGORITHM_RECEIPT_PRIVATE_KEY = test_entry._Env.TRY_OPERATION_RECEIPT_PRIVATE_KEY
    TRY_ALGORITHM_RECEIPT_KEY_ID = "algorithm-test-v1"
    TRY_ALGORITHM_WORKER_ID = "worker-test"
    TRY_ALGORITHM_WORKER_BUILD_SHA256 = "a" * 64
    TRY_ALGORITHM_EXECUTOR_REVISION = "b" * 40
    TRY_ALGORITHM_EXECUTOR_SHA256 = algorithm_entry._executor_source_sha256()


class AlgorithmDurableLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.ctx = FakeContext()
        self.env = AlgorithmEnv()
        self.store = algorithm_entry.AlgorithmExecutionStore(self.ctx, self.env)
        self.body = {
            "contract_id": "CT-1", "permit_id": "PM-1", "execution_id": "EX-1",
            "effect_id": "EF-1", "dispatch_id": "DP-1", "dispatch_digest": "c" * 64,
            "attempt_id": "EX-1:attempt:1", "attempt_number": 1,
            "spec": {"operation": "maze.shortest_path", "version": 1, "max_expansions": 100},
            "input": {"grid": ["S..", ".#.", "..G"]},
        }

    def test_artifact_is_persisted_before_terminal_record_and_replay_is_idempotent(self):
        first = asyncio.run(self.store.execute_once(self.body))
        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(self.ctx.storage.writes[-2:], ["artifact_b64", "record"])
        self.assertEqual(first["record"]["receipt"]["status"], "COMPLETED")
        replay = asyncio.run(self.store.execute_once(self.body))
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["artifact_b64"], first["artifact_b64"])
        self.assertEqual(replay["record"]["receipt"], first["record"]["receipt"])

    def test_identity_conflict_does_not_execute_again(self):
        first = asyncio.run(self.store.execute_once(self.body))
        changed = dict(self.body, dispatch_digest="d" * 64)
        second = asyncio.run(self.store.execute_once(changed))
        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(second, {"status": "CONFLICT", "error": "execution_identity_conflict"})

    def test_preexisting_dispatched_record_is_unknown_and_never_reexecuted(self):
        runtime_input = {"spec": self.body["spec"], "input": self.body["input"]}
        digest = hashlib.sha256(
            algorithm_entry._canonical_json(self.body).encode("utf-8")
        ).hexdigest()
        record = {
            "schema": 1, "contract_id": "CT-1", "permit_id": "PM-1",
            "execution_id": "EX-1", "effect_id": "EF-1", "dispatch_id": "DP-1",
            "dispatch_digest": "c" * 64, "attempt_id": "EX-1:attempt:1",
            "attempt_number": 1, "executor_revision": "b" * 40,
            "executor_sha256": self.env.TRY_ALGORITHM_EXECUTOR_SHA256,
            "spec_sha256": hashlib.sha256(algorithm_entry._canonical_json(runtime_input["spec"]).encode()).hexdigest(),
            "input_sha256": hashlib.sha256(algorithm_entry._canonical_json(runtime_input["input"]).encode()).hexdigest(),
            "status": "UNKNOWN", "execution_state": "IN_PROGRESS_OR_AMBIGUOUS",
            "request_digest": digest,
        }
        asyncio.run(self.ctx.storage.put("record", record))
        result = asyncio.run(self.store.execute_once(self.body))
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["artifact_b64"])
        self.assertEqual(self.ctx.storage.writes, ["record"])

    def test_execution_exception_leaves_durable_unknown_and_replay_does_not_retry(self):
        original = algorithm_entry.execute
        calls = []
        def crash(_):
            calls.append(1)
            raise RuntimeError("simulated post-dispatch crash")
        algorithm_entry.execute = crash
        try:
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                asyncio.run(self.store.execute_once(self.body))
        finally:
            algorithm_entry.execute = original
        result = asyncio.run(self.store.execute_once(self.body))
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(calls, [1])

    def test_runtime_source_pin_mismatch_fails_closed(self):
        env = AlgorithmEnv()
        env.TRY_ALGORITHM_EXECUTOR_SHA256 = "f" * 64
        ready, reason = algorithm_entry._algorithm_readiness(env)
        self.assertFalse(ready)
        self.assertEqual(reason, "algorithm_executor_digest_mismatch")


if __name__ == "__main__":
    unittest.main()
