#!/usr/bin/env python3
"""Append-only solution-lineage recorder.

The governing contract remains external to this module. This module records
provenance; it does not decide policy, evaluation criteria, promotion, or
terminal conditions.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "research" / "lineage.jsonl"

REQUIRED = {
    "experiment_id", "generation", "parent_artifacts", "hypothesis", "change",
    "code_revision", "config_hash", "data_hash", "evaluator", "result",
    "verdict", "evidence", "findings", "constraints", "claims",
}

def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def append_experiment(record: dict) -> dict:
    missing = sorted(REQUIRED - record.keys())
    if missing:
        raise ValueError("missing lineage fields: " + ",".join(missing))
    entry = dict(record)
    entry["record_hash"] = _hash(record)
    entry["recorded_at"] = datetime.now(timezone.utc).isoformat()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry

def read_lineage() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
