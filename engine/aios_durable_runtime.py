"""TRY-owned SQLite durable handoff for AIOS-authorized external effects.

AIOS remains the authority for contracts, permits, effect/attempt identity,
provider receipts, UNKNOWN and retry authorization. This module only persists
scheduler handoffs and worker leases. Expired leases become UNKNOWN; they are
never silently re-queued because the provider may already have acted.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
import time
from pathlib import Path
from typing import Any, Mapping

import engine.aios_path  # noqa: F401  (pins AIOS as `core`)
from core.durable_runtime import DurableRuntime, RuntimeSubmission

from engine.aios_authority_reader import verified_terminal


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
        with closing(self._connect()) as conn:
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
                    unknown_reason TEXT,
                    aios_receipt_json TEXT,
                    PRIMARY KEY(effect_id, attempt_id)
                )
            """)
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(runtime_handoffs)")}
            for col in ("unknown_reason", "aios_receipt_json"):
                if col not in cols:  # forward-migrate databases from the previous slice
                    conn.execute(f"ALTER TABLE runtime_handoffs ADD COLUMN {col} TEXT")
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
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if expected_attempt is not None:
                self._retry_gate(conn, effect_id, attempt_id, expected_attempt)
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

    @staticmethod
    def _retry_gate(conn, effect_id, attempt_id, attempt):
        """A retry row is accepted only after the previous attempt is UNKNOWN here.

        AIOS authorizes the retry (UNKNOWN + bounded attempt budget); this gate
        additionally refuses to schedule attempt N while attempt N-1 is still
        scheduled, claimed by a live worker, or already terminal.
        """
        if attempt_id != f"{effect_id}:attempt:{attempt}":
            raise DurableQueueError("retry attempt_id is not bound to attempt number")
        existing = conn.execute(
            "SELECT status FROM runtime_handoffs WHERE effect_id=? AND attempt_id=?",
            (effect_id, attempt_id),
        ).fetchone()
        if existing is not None:
            return  # idempotent replay; payload equality is checked by caller
        prev = conn.execute(
            "SELECT status FROM runtime_handoffs WHERE effect_id=? AND attempt_id=?",
            (effect_id, f"{effect_id}:attempt:{attempt - 1}"),
        ).fetchone()
        if prev is None or prev["status"] != "UNKNOWN":
            raise DurableQueueError(
                "retry gated: previous attempt must exist and be UNKNOWN in the scheduler "
                f"(got {None if prev is None else prev['status']})"
            )
        others = conn.execute(
            "SELECT COUNT(*) FROM runtime_handoffs WHERE effect_id=? AND status IN "
            "('SUBMITTED','CLAIMED','OBSERVED_SUCCESS','OBSERVED_FAILURE')",
            (effect_id,),
        ).fetchone()[0]
        if others:
            raise DurableQueueError("retry gated: effect has a live or terminal attempt")

    def can_retry(self, *, effect_id: str, attempt: int) -> bool:
        with closing(self._connect()) as conn:
            try:
                self._retry_gate(conn, effect_id, f"{effect_id}:attempt:{attempt}", attempt)
            except DurableQueueError:
                return False
        return True

    def submit(self, *, effect: Mapping[str, Any], attempt_id: str) -> RuntimeSubmission:
        return self._submit(effect, attempt_id)

    def resume(self, *, effect: Mapping[str, Any], attempt_id: str) -> RuntimeSubmission:
        effect_id, attempt_id = self._identity(effect, attempt_id)
        with closing(self._connect()) as conn:
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
        if row["status"] != "SUBMITTED":
            raise DurableQueueError(
                "resume blocked: claimed/unknown/terminal handoff requires worker or AIOS reconciliation"
            )
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
        with closing(self._connect()) as conn:
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
        with closing(self._connect()) as conn:
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
        with closing(self._connect()) as conn:
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

    # ------------------------------------------------------------------
    # Readback / reconciliation helpers
    # ------------------------------------------------------------------
    def get_handoff(self, *, effect_id: str, attempt_id: str):
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM runtime_handoffs WHERE effect_id=? AND attempt_id=?",
                (effect_id, attempt_id),
            ).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["effect"] = json.loads(out.pop("payload_json"))
        return out

    def mark_unknown(self, *, effect_id: str, attempt_id: str, worker_id: str, reason: str):
        """Owner-bound CLAIMED -> UNKNOWN. Never requeues; AIOS must reconcile."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be non-empty")
        now = self._clock()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            changed = conn.execute(
                """UPDATE runtime_handoffs SET status='UNKNOWN',worker_id=NULL,
                   lease_expires_at=NULL,unknown_reason=?,updated_at=?
                   WHERE effect_id=? AND attempt_id=? AND status='CLAIMED' AND worker_id=?""",
                (reason[:2000], now, effect_id, attempt_id, worker_id),
            ).rowcount
            conn.commit()
        return changed == 1

    def mirror_verified_terminal(self, *, aios_dir: str, effect_id: str, attempt_id: str,
                                 worker_id: str | None = None):
        """Mirror an AIOS terminal outcome only after verifying the AIOS receipt.

        There is deliberately no way to pass a state string: the outcome is read
        from the AIOS effect-of-record and its evidence digest is verified. If
        verification fails the row is left untouched (non-terminal) and
        ``AuthorityRejected`` propagates.
        """
        row = self.get_handoff(effect_id=effect_id, attempt_id=attempt_id)
        if row is None:
            raise DurableQueueError("terminal mirror rejected: unknown handoff")
        snapshot = row["effect"]
        verified = verified_terminal(
            aios_dir, effect_id=effect_id, attempt_id=attempt_id, provider=row["provider"],
            expected={k: snapshot[k] for k in ("attempt", "actor", "contract_id", "permit_id",
                                              "effect_type") if k in snapshot},
        )
        now = self._clock()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if worker_id is None:
                where, args = "status='UNKNOWN'", ()
            else:
                where, args = "(status='UNKNOWN' OR (status='CLAIMED' AND worker_id=?))", (worker_id,)
            changed = conn.execute(
                f"""UPDATE runtime_handoffs SET status=?,worker_id=NULL,lease_expires_at=NULL,
                    aios_receipt_json=?,updated_at=?
                    WHERE effect_id=? AND attempt_id=? AND provider=? AND {where}""",
                (verified["state"], json.dumps(verified, sort_keys=True), now,
                 effect_id, attempt_id, row["provider"], *args),
            ).rowcount
            conn.commit()
        if changed != 1:
            raise DurableQueueError("terminal mirror rejected: handoff not in a mirrorable state")
        return verified
