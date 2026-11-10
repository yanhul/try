"""TRY-owned SQLite durable handoff for AIOS-authorized external effects.

AIOS remains the authority for contracts, permits, effect/attempt identity,
provider receipts, UNKNOWN and retry authorization. This module only persists
scheduler handoffs and worker leases. Expired leases become UNKNOWN; they are
never silently re-queued because the provider may already have acted.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping

from core.durable_runtime import DurableRuntime, RuntimeSubmission


class DurableQueueError(RuntimeError):
    pass


class TrySQLiteDurableRuntime(DurableRuntime):
    """SQLite/WAL scheduler adapter implementing AIOS DurableRuntime.

    A worker must call claim()/heartbeat() and then invoke the AIOS execution
    boundary. This class does not call providers or grant execution authority.
    """

    name = "try-sqlite-durable-runtime"

    def __init__(self, database: str | Path, *, provider_name: str,
                 lease_seconds: int = 90, clock=time.time):
        if not isinstance(provider_name, str) or not provider_name.strip():
            raise ValueError("provider_name must be non-empty")
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be a positive integer")
        self.database = str(database)
        self.provider_name = provider_name
        self.lease_seconds = lease_seconds
        self._clock = clock
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(self.database, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _initialize(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runtime_handoffs (
                    effect_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('SUBMITTED','CLAIMED','UNKNOWN','OBSERVED_SUCCESS','OBSERVED_FAILURE')),
                    worker_id TEXT,
                    lease_expires_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(effect_id, attempt_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_runtime_handoffs_claim
                ON runtime_handoffs(status, created_at)
            """)

    @staticmethod
    def _identity(effect: Mapping[str, Any], attempt_id: str):
        if not isinstance(effect, Mapping):
            raise ValueError("effect must be a mapping")
        effect_id = effect.get("effect_id")
        if not isinstance(effect_id, str) or not effect_id.strip():
            raise ValueError("effect.effect_id must be non-empty")
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            raise ValueError("attempt_id must be non-empty")
        if effect.get("attempt_id") != attempt_id:
            raise DurableQueueError("effect/attempt identity mismatch")
        if effect.get("state") != "DISPATCHED":
            raise DurableQueueError("only AIOS-dispatched effects may be submitted")
        return effect_id, attempt_id

    def _submit(self, effect, attempt_id, *, expected_attempt=None):
        effect_id, attempt_id = self._identity(effect, attempt_id)
        if expected_attempt is not None:
            if effect.get("attempt") != expected_attempt:
                raise DurableQueueError("retry attempt number mismatch")
        if effect.get("provider") != self.provider_name:
            raise DurableQueueError("effect provider does not match configured provider")
        payload = json.dumps(dict(effect), sort_keys=True, separators=(",", ":"))
        now = self._clock()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM runtime_handoffs WHERE effect_id=? AND attempt_id=?",
                (effect_id, attempt_id),
            ).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO runtime_handoffs
                    (effect_id,attempt_id,provider,payload_json,status,created_at,updated_at)
                    VALUES (?,?,?,?, 'SUBMITTED', ?, ?)""",
                    (effect_id, attempt_id, self.provider_name, payload, now, now),
                )
            elif row["provider"] != self.provider_name or row["payload_json"] != payload:
                raise DurableQueueError("handoff identity collision with different payload")
            conn.commit()
        return RuntimeSubmission(effect_id, attempt_id, self.provider_name)

    def submit(self, *, effect: Mapping[str, Any], attempt_id: str) -> RuntimeSubmission:
        return self._submit(effect, attempt_id)

    def resume(self, *, effect: Mapping[str, Any], attempt_id: str) -> RuntimeSubmission:
        effect_id, attempt_id = self._identity(effect, attempt_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runtime_handoffs WHERE effect_id=? AND attempt_id=?",
                (effect_id, attempt_id),
            ).fetchone()
        if row is None:
            raise DurableQueueError("cannot resume an unknown handoff")
        if row["provider"] != self.provider_name or row["payload_json"] != json.dumps(
            dict(effect), sort_keys=True, separators=(",", ":")
        ):
            raise DurableQueueError("resume identity/payload mismatch")
        if row["status"] in ("OBSERVED_SUCCESS", "OBSERVED_FAILURE"):
            raise DurableQueueError("cannot resume an observed terminal handoff")
        return RuntimeSubmission(effect_id, attempt_id, self.provider_name)

    def retry(self, *, effect: Mapping[str, Any], attempt_id: str,
              attempt: int) -> RuntimeSubmission:
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 2:
            raise ValueError("retry attempt must be an integer >= 2")
        return self._submit(effect, attempt_id, expected_attempt=attempt)

    def claim(self, *, worker_id: str):
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be non-empty")
        now = self._clock()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM runtime_handoffs WHERE status='SUBMITTED' "
                "ORDER BY created_at,effect_id,attempt_id LIMIT 1"
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            expiry = now + self.lease_seconds
            changed = conn.execute(
                """UPDATE runtime_handoffs SET status='CLAIMED',worker_id=?,
                   lease_expires_at=?,updated_at=?
                   WHERE effect_id=? AND attempt_id=? AND status='SUBMITTED'""",
                (worker_id, expiry, now, row["effect_id"], row["attempt_id"]),
            ).rowcount
            conn.commit()
            if changed != 1:
                return None
            return {
                "effect_id": row["effect_id"], "attempt_id": row["attempt_id"],
                "provider": row["provider"], "effect": json.loads(row["payload_json"]),
                "worker_id": worker_id, "lease_expires_at": expiry,
            }

    def heartbeat(self, *, effect_id: str, attempt_id: str, worker_id: str):
        now = self._clock()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            changed = conn.execute(
                """UPDATE runtime_handoffs SET lease_expires_at=?,updated_at=?
                   WHERE effect_id=? AND attempt_id=? AND status='CLAIMED'
                   AND worker_id=? AND lease_expires_at>?""",
                (now + self.lease_seconds, now, effect_id, attempt_id, worker_id, now),
            ).rowcount
            conn.commit()
        if changed != 1:
            raise DurableQueueError("heartbeat rejected: lease missing, expired, or owned by another worker")
        return now + self.lease_seconds

    def recover_expired_leases(self):
        """Fail closed: an expired worker lease is UNKNOWN, never automatically requeued."""
        now = self._clock()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """SELECT effect_id,attempt_id FROM runtime_handoffs
                   WHERE status='CLAIMED' AND lease_expires_at<=?""", (now,)
            ).fetchall()
            conn.execute(
                """UPDATE runtime_handoffs SET status='UNKNOWN',worker_id=NULL,
                   lease_expires_at=NULL,updated_at=?
                   WHERE status='CLAIMED' AND lease_expires_at<=?""", (now, now)
            )
            conn.commit()
        return [(r["effect_id"], r["attempt_id"]) for r in rows]

    def mark_aios_terminal(self, *, effect_id: str, attempt_id: str, state: str):
        """Mirror an AIOS terminal state only after AIOS has durably recorded it."""
        if state not in ("OBSERVED_SUCCESS", "OBSERVED_FAILURE"):
            raise ValueError("state must be an AIOS observed terminal state")
        now = self._clock()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            changed = conn.execute(
                """UPDATE runtime_handoffs SET status=?,worker_id=NULL,
                   lease_expires_at=NULL,updated_at=?
                   WHERE effect_id=? AND attempt_id=? AND status IN ('CLAIMED','UNKNOWN')""",
                (state, now, effect_id, attempt_id),
            ).rowcount
            conn.commit()
        if changed != 1:
            raise DurableQueueError("terminal mirror rejected: handoff not claimable")
        return state
