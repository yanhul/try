"""TRY-owned SQLite worker queue behind the AIOS authority boundary.

Adapted Javis OS lifecycle primitives: atomic claim, lease/heartbeat,
monotonic checkpoint and durable observation. Expired ambiguous work becomes
UNKNOWN and is never silently requeued. No automatic retry or authority grant.
"""
from __future__ import annotations
from contextlib import contextmanager
import json
import sqlite3
import time
from pathlib import Path
from typing import Callable, Mapping

class WorkerQueueError(RuntimeError):
    pass

class WorkerJobStore:
    def __init__(self, path: str | Path, authority_verifier: Callable[[str, str], object]):
        self.path = str(path)
        self.authority_verifier = authority_verifier
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS worker_jobs (
                task_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                contract_id TEXT NOT NULL, permit_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                status TEXT NOT NULL, worker_id TEXT NOT NULL DEFAULT '',
                lease_until REAL NOT NULL DEFAULT 0, heartbeat_at REAL NOT NULL DEFAULT 0,
                checkpoint INTEGER NOT NULL DEFAULT 0, evidence_ref TEXT NOT NULL DEFAULT '',
                block_reason TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL
            )""")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=10000")
        try:
            yield db
        finally:
            db.close()

    def _authorize(self, contract_id, permit_id):
        result = self.authority_verifier(contract_id, permit_id)
        if result is False or result is None:
            raise PermissionError("AIOS authority verification did not authorize this operation")

    def enqueue(self, *, task_id, idempotency_key, contract_id, permit_id, payload: Mapping[str, object]):
        if not all(isinstance(v, str) and v.strip() for v in (task_id, idempotency_key, contract_id, permit_id)):
            raise ValueError("task and authority identities are required")
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")
        self._authorize(contract_id, permit_id)
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("""INSERT INTO worker_jobs
                    (task_id,idempotency_key,contract_id,permit_id,payload_json,status,created_at,updated_at)
                    VALUES (?,?,?,?,?,'QUEUED',?,?)""",
                    (task_id,idempotency_key,contract_id,permit_id,
                     json.dumps(dict(payload),sort_keys=True,separators=(",",":")),now,now))
                db.commit()
            except Exception:
                db.rollback()
                raise

    def claim(self, *, worker_id: str, lease_seconds: float):
        if not worker_id.strip() or lease_seconds <= 0:
            raise ValueError("worker_id and positive lease_seconds are required")
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE worker_jobs SET status='UNKNOWN',
                block_reason='lease_expired_ambiguous',updated_at=?
                WHERE status IN ('CLAIMED','RUNNING') AND lease_until<=?""", (now,now))
            row = db.execute("SELECT * FROM worker_jobs WHERE status='QUEUED' ORDER BY created_at,task_id LIMIT 1").fetchone()
            if row is None:
                db.commit()
                return None
            self._authorize(row["contract_id"], row["permit_id"])
            changed = db.execute("""UPDATE worker_jobs SET status='CLAIMED',worker_id=?,
                lease_until=?,heartbeat_at=?,updated_at=? WHERE task_id=? AND status='QUEUED'""",
                (worker_id,now+lease_seconds,now,now,row["task_id"])).rowcount
            db.commit()
            return self.get(row["task_id"]) if changed == 1 else None

    def _owned_row(self, db, task_id, worker_id):
        row = db.execute("SELECT * FROM worker_jobs WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        self._authorize(row["contract_id"], row["permit_id"])
        if row["worker_id"] != worker_id or row["status"] not in ("CLAIMED","RUNNING") or row["lease_until"] <= time.time():
            raise WorkerQueueError("worker does not own a live lease")
        return row

    def heartbeat(self, *, task_id, worker_id, lease_seconds):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned_row(db,task_id,worker_id)
            changed = db.execute("""UPDATE worker_jobs SET status='RUNNING',heartbeat_at=?,lease_until=?,updated_at=?
                WHERE task_id=? AND worker_id=? AND status IN ('CLAIMED','RUNNING') AND lease_until>?""",
                (now,now+lease_seconds,now,task_id,worker_id,now)).rowcount
            if changed != 1:
                db.rollback()
                raise WorkerQueueError("worker lease expired during heartbeat")
            db.commit()

    def checkpoint(self, *, task_id, worker_id, checkpoint):
        if not isinstance(checkpoint,int) or isinstance(checkpoint,bool) or checkpoint < 0:
            raise ValueError("checkpoint must be a non-negative integer")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._owned_row(db,task_id,worker_id)
            if checkpoint < row["checkpoint"]:
                db.rollback()
                raise WorkerQueueError("checkpoint must be monotonic")
            changed = db.execute("""UPDATE worker_jobs SET checkpoint=?,updated_at=?
                WHERE task_id=? AND worker_id=? AND status IN ('CLAIMED','RUNNING')
                  AND lease_until>? AND checkpoint<=?""",
                (checkpoint,time.time(),task_id,worker_id,time.time(),checkpoint)).rowcount
            if changed != 1:
                db.rollback()
                raise WorkerQueueError("checkpoint update lost its live lease")
            db.commit()

    def observe(self, *, task_id, worker_id, evidence_ref):
        if not isinstance(evidence_ref,str) or not evidence_ref.strip():
            raise ValueError("OBSERVED requires an evidence reference")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned_row(db,task_id,worker_id)
            changed = db.execute("""UPDATE worker_jobs SET status='OBSERVED',evidence_ref=?,updated_at=?
                WHERE task_id=? AND worker_id=? AND status IN ('CLAIMED','RUNNING') AND lease_until>?""",
                (evidence_ref,time.time(),task_id,worker_id,time.time())).rowcount
            if changed != 1:
                db.rollback()
                raise WorkerQueueError("worker lease expired before observation")
            db.commit()

    def mark_unknown(self, *, task_id, worker_id, reason):
        if not isinstance(reason,str) or not reason.strip():
            raise ValueError("UNKNOWN requires a reason")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned_row(db,task_id,worker_id)
            changed = db.execute("""UPDATE worker_jobs SET status='UNKNOWN',block_reason=?,updated_at=?
                WHERE task_id=? AND worker_id=? AND status IN ('CLAIMED','RUNNING')""",
                (reason,time.time(),task_id,worker_id)).rowcount
            if changed != 1:
                db.rollback()
                raise WorkerQueueError("worker no longer owns the active job")
            db.commit()

    def get(self, task_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM worker_jobs WHERE task_id=?", (task_id,)).fetchone()
            return dict(row) if row else None
