"""Real-adapter integration: pinned AIOS authority store + TrySQLiteDurableRuntime.

No RecordingRuntime here: every test uses the real SQLite/WAL adapter and the
real AIOS file-backed authority store. Providers are local fixtures; the crash
test kills a real child process after a local side effect (see its docstring
for what this does and does not prove).
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import core
from core.authority import persist_contract, persist_permit
from core.capabilities import Capability, CapabilityRegistry
from core.contract import contract_identity
from core.effect_authority import retry_dispatch, unknown
from core.evidence import EvidenceRecord
from core.external_effect import load_effects
from core.policy_registry import persist_policy
from core.runtime import ProviderReceipt, execute

from engine import aios_durable_worker as worker_mod
from engine.aios_authority_reader import AuthorityRejected
from engine.aios_durable_runtime import DurableQueueError, TrySQLiteDurableRuntime
from engine.aios_durable_worker import AiosDurableWorker, enqueue_dispatched, enqueue_retry

PROVIDER = "try-integration-fixture"
ACTOR = "agent:try-integration"
REPO_ROOT = Path(__file__).resolve().parents[1]
AIOS_ROOT = Path(core.__file__).resolve().parents[1]


class Clock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class LedgerProvider:
    """Provider fixture whose side effect is a durable, fsync'd local ledger line."""

    name = PROVIDER

    def __init__(self, ledger: Path, *, outcome="OBSERVED_SUCCESS", fail=False):
        self.ledger = ledger
        self.outcome = outcome
        self.fail = fail
        self.calls = 0

    def execute(self, *, contract, effect, attempt_id):
        self.calls += 1
        with open(self.ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"effect_id": effect["effect_id"], "attempt_id": attempt_id}) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        if self.fail:
            raise TimeoutError("fixture provider timeout")
        return ProviderReceipt(provider=self.name, effect_id=effect["effect_id"],
                               attempt_id=attempt_id, provider_operation_id=f"op-{attempt_id}",
                               outcome=self.outcome, observation={"ledger": str(self.ledger)})


def side_effects(ledger: Path) -> int:
    if not ledger.exists():
        return 0
    return sum(1 for line in ledger.read_text().splitlines() if line.strip())


def make_authority(root: str, *, max_attempts=2) -> tuple[str, str]:
    registry = CapabilityRegistry()
    registry.register(Capability(PROVIDER, "1", "TRY integration test", "provider", status="ACTIVE"))
    registry.persist(root, "TRY integration test")
    policy_digest = persist_policy(
        root, {"policy_type": "GOVERNING_POLICY", "name": "try-durable-runtime-worker"})
    contract = {
        "contract_type": "EXECUTION_CONTRACT", "task_id": "try-durable-runtime-worker",
        "scope": "cross-repository-test", "actor": ACTOR,
        "capabilities": [f"{PROVIDER}@1"], "input_digest": "fixture-input-v1",
        "allowed_effects": ["external_effect"], "evidence_required": ["provider_receipt"],
        "max_attempts": max_attempts, "terminal_states": ["SUCCESS", "FAILURE"],
        "policy_digest": policy_digest,
    }
    persist_contract(root, contract)
    permit = persist_permit(root, contract, "root")
    return contract_identity(contract), permit["permit_id"]


class Env:
    def __init__(self, tmp: str, *, max_attempts=2, lease_seconds=30):
        self.tmp = Path(tmp)
        self.aios = self.tmp / "aios"
        self.aios.mkdir()
        self.ledger = self.tmp / "provider-ledger.jsonl"
        self.db = self.tmp / "queue" / "runtime.sqlite3"
        self.clock = Clock()
        self.contract_id, self.permit_id = make_authority(str(self.aios), max_attempts=max_attempts)
        self.runtime = TrySQLiteDurableRuntime(self.db, provider_name=PROVIDER,
                                               lease_seconds=lease_seconds, clock=self.clock)

    def worker(self, provider=None, *, actor=ACTOR, worker_id="worker-a"):
        return AiosDurableWorker(aios_dir=self.aios, runtime=self.runtime,
                                 adapter=provider or LedgerProvider(self.ledger),
                                 actor=actor, worker_id=worker_id)

    def enqueue(self, op="op-1"):
        return enqueue_dispatched(self.aios, self.contract_id, self.permit_id, op, ACTOR, self.runtime)

    def aios_effect(self, effect_id):
        return load_effects(str(self.aios))[effect_id]

    def row(self, effect_id, attempt=1):
        return self.runtime.get_handoff(effect_id=effect_id, attempt_id=f"{effect_id}:attempt:{attempt}")

    def tamper_row_payload(self, effect_id, **changes):
        attempt_id = f"{effect_id}:attempt:1"
        with sqlite3.connect(self.db) as conn:
            payload = json.loads(conn.execute(
                "SELECT payload_json FROM runtime_handoffs WHERE effect_id=? AND attempt_id=?",
                (effect_id, attempt_id)).fetchone()[0])
            payload.update(changes)
            conn.execute("UPDATE runtime_handoffs SET payload_json=? WHERE effect_id=? AND attempt_id=?",
                         (json.dumps(payload, sort_keys=True, separators=(",", ":")), effect_id, attempt_id))

    def effect_path(self, effect_id):
        return self.aios / "effects" / f"{effect_id}.json"


class InProcessExecuteWithRealAdapterTest(unittest.TestCase):
    def test_aios_execute_persists_handoff_in_sqlite_and_worker_never_reexecutes(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            provider = LedgerProvider(env.ledger)
            result = execute(str(env.aios), env.contract_id, env.permit_id, "op-inproc", ACTOR,
                             provider, env.runtime)
            self.assertEqual(result["state"], "OBSERVED_SUCCESS")
            eid, aid = result["effect_id"], result["attempt_id"]
            row = env.row(eid)
            # Persisted handoff identity + readback.
            self.assertEqual((row["effect_id"], row["attempt_id"], row["provider"]), (eid, aid, PROVIDER))
            self.assertEqual(row["status"], "SUBMITTED")
            for field in ("effect_id", "attempt_id", "attempt", "provider", "actor",
                          "contract_id", "permit_id"):
                self.assertEqual(row["effect"][field], result[field], field)
            self.assertEqual(row["effect"]["state"], "DISPATCHED")
            # A worker claiming the stale SUBMITTED row must not call the provider again.
            second = LedgerProvider(env.ledger)
            out = env.worker(second).run_once()
            self.assertFalse(out.execution_attempted)
            self.assertEqual(second.calls, 0)
            self.assertEqual(side_effects(env.ledger), 1)
            self.assertEqual(out.queue_status, "OBSERVED_SUCCESS")
            receipt = json.loads(env.row(eid)["aios_receipt_json"])
            self.assertEqual(receipt["evidence_digest"],
                             result["provider_observation"]["evidence"]["digest"])

    def test_aios_execute_ambiguous_outcome_mirrors_unknown_not_terminal(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            result = execute(str(env.aios), env.contract_id, env.permit_id, "op-timeout", ACTOR,
                             LedgerProvider(env.ledger, fail=True), env.runtime)
            self.assertEqual(result["state"], "UNKNOWN")
            out = env.worker().run_once()
            self.assertFalse(out.execution_attempted)
            self.assertEqual(out.queue_status, "UNKNOWN")
            self.assertEqual(side_effects(env.ledger), 1)
            self.assertIsNone(env.worker().run_once())


class WorkerPathTest(unittest.TestCase):
    def test_worker_executes_only_after_authoritative_read_and_mirrors_verified_receipt(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            effect = env.enqueue()
            self.assertEqual(side_effects(env.ledger), 0)  # enqueue never calls provider
            provider = LedgerProvider(env.ledger)
            with mock.patch.object(worker_mod, "authoritative_dispatch",
                                   wraps=worker_mod.authoritative_dispatch) as spy:
                out = env.worker(provider).run_once()
            spy.assert_called_once()
            self.assertTrue(out.execution_attempted)
            self.assertEqual(provider.calls, 1)
            self.assertEqual(out.queue_status, "OBSERVED_SUCCESS")
            aios = env.aios_effect(effect["effect_id"])
            self.assertEqual(aios["state"], "OBSERVED_SUCCESS")
            receipt = json.loads(env.row(effect["effect_id"])["aios_receipt_json"])
            self.assertEqual(receipt["evidence_digest"], aios["provider_observation"]["evidence"]["digest"])
            self.assertEqual(receipt["state"], aios["state"])
            self.assertIsNone(env.worker().run_once())

    def test_worker_mirrors_observed_failure_from_aios_not_from_caller(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            effect = env.enqueue()
            out = env.worker(LedgerProvider(env.ledger, outcome="OBSERVED_FAILURE")).run_once()
            self.assertEqual(out.queue_status, "OBSERVED_FAILURE")
            self.assertEqual(env.aios_effect(effect["effect_id"])["state"], "OBSERVED_FAILURE")

    def test_provider_ambiguity_is_unknown_in_both_stores_and_never_requeued(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            effect = env.enqueue()
            out = env.worker(LedgerProvider(env.ledger, fail=True)).run_once()
            self.assertEqual(out.queue_status, "UNKNOWN")
            self.assertEqual(env.aios_effect(effect["effect_id"])["state"], "UNKNOWN")
            self.assertIsNone(env.worker(worker_id="worker-b").run_once())
            self.assertEqual(side_effects(env.ledger), 1)

    def test_aios_persistence_failure_after_provider_is_unknown(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            effect = env.enqueue()
            with mock.patch("core.runtime.observe", side_effect=OSError("disk full")):
                out = env.worker().run_once()
            self.assertTrue(out.execution_attempted)
            self.assertEqual(out.queue_status, "UNKNOWN")
            self.assertIn("disk full", out.reason)
            self.assertEqual(env.aios_effect(effect["effect_id"])["state"], "DISPATCHED")
            self.assertEqual(side_effects(env.ledger), 1)
            self.assertIsNone(env.worker().run_once())


class StaleOrMismatchedAuthorityTest(unittest.TestCase):
    def assert_rejected_without_provider(self, env, effect_id, provider=None, **worker_kw):
        provider = provider or LedgerProvider(env.ledger)
        out = env.worker(provider, **worker_kw).run_once()
        self.assertIsNotNone(out)
        self.assertFalse(out.execution_attempted, out.reason)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(side_effects(env.ledger), 0)
        self.assertEqual(out.queue_status, "UNKNOWN")
        self.assertEqual(env.row(effect_id)["status"], "UNKNOWN")
        return out

    def test_stale_aios_state_unknown_blocks_provider(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            unknown(str(env.aios), eid, ACTOR, "operator marked ambiguous")
            out = self.assert_rejected_without_provider(env, eid)
            self.assertIn("not DISPATCHED", out.reason)

    def test_stale_snapshot_for_superseded_attempt_blocks_provider(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            unknown(str(env.aios), eid, ACTOR, "ambiguous")
            retry_dispatch(str(env.aios), eid, ACTOR, f"{eid}:attempt:2", PROVIDER, 2)
            self.assertEqual(env.aios_effect(eid)["state"], "DISPATCHED")  # but for attempt 2
            out = self.assert_rejected_without_provider(env, eid)
            self.assertIn("attempt", out.reason)

    def test_missing_effect_of_record_blocks_provider(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            env.effect_path(eid).unlink()
            out = self.assert_rejected_without_provider(env, eid)
            self.assertIn("no effect-of-record", out.reason)

    def test_unreadable_authority_blocks_provider(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            env.effect_path(eid).write_text("{not json")
            out = self.assert_rejected_without_provider(env, eid)
            self.assertIn("unreadable", out.reason)

    def test_revoked_permit_blocks_provider(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            (env.aios / "authority" / "permits" / f"{env.permit_id}.json").unlink()
            out = self.assert_rejected_without_provider(env, eid)
            self.assertIn("contract/permit rejected", out.reason)

    def test_missing_authority_root_fails_closed_at_worker_start(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            with self.assertRaises(AuthorityRejected):
                AiosDurableWorker(aios_dir=env.tmp / "nope", runtime=env.runtime,
                                  adapter=LedgerProvider(env.ledger), actor=ACTOR, worker_id="w")

    def test_mismatched_snapshot_fields_block_provider(self):
        cases = {
            "attempt": {"attempt": 2},
            "contract": {"contract_id": "CT-forged"},
            "permit": {"permit_id": "PM-forged"},
            "actor": {"actor": "agent:other"},
            "provider": {"provider": "other-provider"},
        }
        for name, changes in cases.items():
            with self.subTest(name), TemporaryDirectory() as tmp:
                env = Env(tmp)
                eid = env.enqueue()["effect_id"]
                env.tamper_row_payload(eid, **changes)
                self.assert_rejected_without_provider(env, eid)

    def test_worker_actor_mismatch_blocks_provider(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            self.assert_rejected_without_provider(env, eid, actor="agent:intruder")

    def test_provider_mismatch_rejected_at_worker_construction(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            other = LedgerProvider(env.ledger)
            other.name = "other-provider"
            with self.assertRaises(ValueError):
                env.worker(other)


class TerminalMirrorTest(unittest.TestCase):
    def _claimed_unknown(self, env):
        eid = env.enqueue()["effect_id"]
        claim = env.runtime.claim(worker_id="worker-a")
        env.runtime.mark_unknown(effect_id=eid, attempt_id=claim["attempt_id"],
                                 worker_id="worker-a", reason="test")
        return eid, claim["attempt_id"]

    def _forge(self, env, eid, attempt_id, *, run_id=None, digest_ok=True, state="OBSERVED_SUCCESS"):
        rec = json.loads(env.effect_path(eid).read_text())
        ev = EvidenceRecord(evidence_id="EV-forged", level="OBSERVED", source_ref="forged://x",
                            claim="forged", run_id=run_id or attempt_id, provider=PROVIDER).as_record()
        if not digest_ok:
            ev["digest"] = "0" * 64
        rec["state"] = state
        rec["provider_observation"] = {"provider": PROVIDER, "provider_operation_id": "forged",
                                       "effect_id": eid, "attempt_id": attempt_id,
                                       "observation": {"forged": True}, "evidence": ev}
        env.effect_path(eid).write_text(json.dumps(rec))

    def test_mirror_rejected_while_aios_not_terminal(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            claim = env.runtime.claim(worker_id="worker-a")
            with self.assertRaises(AuthorityRejected):
                env.runtime.mirror_verified_terminal(aios_dir=str(env.aios), effect_id=eid,
                                                     attempt_id=claim["attempt_id"], worker_id="worker-a")
            self.assertEqual(env.row(eid)["status"], "CLAIMED")

    def test_forged_terminal_with_bad_evidence_digest_rejected(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid, aid = self._claimed_unknown(env)
            self._forge(env, eid, aid, digest_ok=False)
            with self.assertRaises(AuthorityRejected):
                env.runtime.mirror_verified_terminal(aios_dir=str(env.aios), effect_id=eid, attempt_id=aid)
            self.assertEqual(env.row(eid)["status"], "UNKNOWN")
            self.assertIsNone(env.row(eid)["aios_receipt_json"])

    def test_terminal_evidence_bound_to_other_attempt_rejected(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid, aid = self._claimed_unknown(env)
            self._forge(env, eid, aid, run_id=f"{eid}:attempt:9")
            with self.assertRaises(AuthorityRejected):
                env.runtime.mirror_verified_terminal(aios_dir=str(env.aios), effect_id=eid, attempt_id=aid)
            self.assertEqual(env.row(eid)["status"], "UNKNOWN")

    def test_other_worker_cannot_mirror_claimed_row(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            result = execute(str(env.aios), env.contract_id, env.permit_id, "op-x", ACTOR,
                             LedgerProvider(env.ledger), env.runtime)
            env.runtime.claim(worker_id="worker-a")
            with self.assertRaises(DurableQueueError):
                env.runtime.mirror_verified_terminal(aios_dir=str(env.aios),
                                                     effect_id=result["effect_id"],
                                                     attempt_id=result["attempt_id"],
                                                     worker_id="worker-b")
            self.assertEqual(env.row(result["effect_id"])["status"], "CLAIMED")


class LeaseAndRetryTest(unittest.TestCase):
    def test_expired_lease_is_unknown_never_requeued_and_aios_untouched(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            env.runtime.claim(worker_id="worker-dead")  # worker dies before provider
            env.clock.advance(31)
            self.assertEqual(env.runtime.recover_expired_leases(), [(eid, f"{eid}:attempt:1")])
            provider = LedgerProvider(env.ledger)
            self.assertIsNone(env.worker(provider).run_once())
            self.assertEqual(provider.calls, 0)
            self.assertEqual(env.row(eid)["status"], "UNKNOWN")
            self.assertEqual(env.aios_effect(eid)["state"], "DISPATCHED")
            # AIOS has not authorized a retry (still DISPATCHED): retry refused.
            with self.assertRaises(RuntimeError):
                enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 2, env.runtime)

    def test_lease_lost_between_authority_read_and_provider_call_skips_provider(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            real = worker_mod.authoritative_dispatch

            def slow_read(*a, **kw):
                out = real(*a, **kw)
                env.clock.advance(31)  # lease expires during the authority read
                return out

            provider = LedgerProvider(env.ledger)
            with mock.patch.object(worker_mod, "authoritative_dispatch", side_effect=slow_read):
                out = env.worker(provider).run_once()
            self.assertFalse(out.execution_attempted)
            self.assertEqual(provider.calls, 0)
            self.assertIn("lease lost", out.reason)
            env.runtime.recover_expired_leases()
            self.assertEqual(env.row(eid)["status"], "UNKNOWN")

    def test_explicit_bounded_retry_after_aios_unknown(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp, max_attempts=2)
            eid = env.enqueue()["effect_id"]
            env.worker(LedgerProvider(env.ledger, fail=True)).run_once()
            self.assertEqual(env.aios_effect(eid)["state"], "UNKNOWN")
            dispatched = enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 2, env.runtime)
            self.assertEqual(dispatched["attempt_id"], f"{eid}:attempt:2")
            self.assertEqual(env.row(eid, 2)["status"], "SUBMITTED")
            out = env.worker().run_once()
            self.assertEqual((out.attempt_id, out.queue_status), (f"{eid}:attempt:2", "OBSERVED_SUCCESS"))
            self.assertEqual(side_effects(env.ledger), 2)
            with self.assertRaises(Exception):  # terminal in AIOS; budget also exhausted
                enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 3, env.runtime)

    def test_retry_beyond_aios_budget_refused(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp, max_attempts=1)
            eid = env.enqueue()["effect_id"]
            env.worker(LedgerProvider(env.ledger, fail=True)).run_once()
            with self.assertRaises(Exception):
                enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 2, env.runtime)
            self.assertIsNone(env.row(eid, 2))
            self.assertEqual(env.aios_effect(eid)["attempt"], 1)

    def test_scheduler_gate_refuses_retry_without_consuming_aios_attempt(self):
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            env.runtime.claim(worker_id="worker-a")  # live lease on attempt 1
            unknown(str(env.aios), eid, ACTOR, "operator marked ambiguous")
            with self.assertRaises(DurableQueueError):
                enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 2, env.runtime)
            aios = env.aios_effect(eid)
            self.assertEqual((aios["state"], aios["attempt"]), ("UNKNOWN", 1))
            self.assertIsNone(env.row(eid, 2))


_CRASH_CHILD = textwrap.dedent('''
    import json, os, sys
    from pathlib import Path
    from core.runtime import ProviderReceipt
    from engine.aios_durable_runtime import TrySQLiteDurableRuntime
    from engine.aios_durable_worker import AiosDurableWorker

    aios, db, ledger, provider_name, actor = sys.argv[1:6]

    class CrashAfterSideEffect:
        name = provider_name
        def execute(self, *, contract, effect, attempt_id):
            with open(ledger, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"effect_id": effect["effect_id"], "attempt_id": attempt_id}) + "\\n")
                fh.flush(); os.fsync(fh.fileno())
            os._exit(137)  # hard process death: no AIOS observe/unknown, no SQLite update

    runtime = TrySQLiteDurableRuntime(db, provider_name=provider_name, lease_seconds=30)
    AiosDurableWorker(aios_dir=aios, runtime=runtime, adapter=CrashAfterSideEffect(),
                      actor=actor, worker_id="worker-crash").run_once()
    sys.exit(3)  # unreachable unless the provider was never called
''')


class CrashWindowTest(unittest.TestCase):
    def test_process_death_after_provider_side_effect_before_aios_receipt(self):
        """Real child-process kill after a durable local side effect.

        Proves: no automatic re-execution, no fabricated terminal mirror, and a
        retry requires an explicit AIOS UNKNOWN decision. Does NOT prove
        exactly-once: the side effect is a local ledger, and an explicitly
        authorized retry re-runs it (asserted below) unless the real provider
        deduplicates by attempt/effect id.
        """
        with TemporaryDirectory() as tmp:
            env = Env(tmp)
            eid = env.enqueue()["effect_id"]
            proc = subprocess.run(
                [sys.executable, "-c", _CRASH_CHILD, str(env.aios), str(env.db),
                 str(env.ledger), PROVIDER, ACTOR],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
                env={**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO_ROOT), str(AIOS_ROOT)])},
            )
            self.assertEqual(proc.returncode, 137, proc.stderr)
            self.assertEqual(side_effects(env.ledger), 1)
            self.assertEqual(env.aios_effect(eid)["state"], "DISPATCHED")  # receipt never persisted
            self.assertNotIn("provider_observation", env.aios_effect(eid))
            self.assertEqual(env.row(eid)["status"], "CLAIMED")

            # Parent clock is past the child's wall-clock lease.
            env.clock.value = env.row(eid)["lease_expires_at"] + 1
            self.assertEqual(env.runtime.recover_expired_leases(), [(eid, f"{eid}:attempt:1")])
            provider = LedgerProvider(env.ledger)
            self.assertIsNone(env.worker(provider).run_once())
            with self.assertRaises(AuthorityRejected):
                env.runtime.mirror_verified_terminal(aios_dir=str(env.aios), effect_id=eid,
                                                     attempt_id=f"{eid}:attempt:1")
            with self.assertRaises(RuntimeError):
                enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 2, env.runtime)
            self.assertEqual(provider.calls, 0)
            self.assertEqual(side_effects(env.ledger), 1)

            # Explicit operator/AIOS decision is the only path to re-execution,
            # and it duplicates a non-idempotent side effect: documented limitation.
            unknown(str(env.aios), eid, ACTOR, "reconciled: worker died after provider call")
            enqueue_retry(env.aios, env.contract_id, env.permit_id, eid, ACTOR, 2, env.runtime)
            out = env.worker().run_once()
            self.assertEqual(out.queue_status, "OBSERVED_SUCCESS")
            self.assertEqual(side_effects(env.ledger), 2)


if __name__ == "__main__":
    unittest.main()
