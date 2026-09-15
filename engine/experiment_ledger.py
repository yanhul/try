"""Durable, append-only experiment ledger primitives.

The ledger records research attempts and search preferences as evidence. It never
asserts promotion authority; final promotion belongs to the Research/AIOS gate.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib, json
from pathlib import Path
from typing import Any, Mapping

STATUSES = frozenset({"PROPOSED", "RUNNING", "SUCCEEDED", "FAILED", "CRASHED", "INVALID", "REJECTED", "RANKED", "PROMOTED"})

def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def identity_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    hypothesis_id: str
    status: str
    parent_experiment_id: str | None = None
    code_revision: str | None = None
    dataset_identity: str | None = None
    configuration_identity: str | None = None
    budget: Mapping[str, Any] | None = None
    result: Mapping[str, Any] | None = None
    failure_class: str | None = None
    decision: str | None = None
    evidence_refs: tuple[str, ...] = ()
    timestamp: str = ""
    def __post_init__(self) -> None:
        if not self.experiment_id.strip() or not self.hypothesis_id.strip():
            raise ValueError("experiment_id and hypothesis_id are required")
        if self.status not in STATUSES:
            raise ValueError(f"invalid experiment status: {self.status}")
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc).isoformat())

class JsonlExperimentLedger:
    """Append-only JSONL ledger. Existing records are never rewritten."""
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
    def append(self, record: ExperimentRecord) -> str:
        payload = asdict(record); payload["evidence_refs"] = list(record.evidence_refs); payload["record_hash"] = identity_hash(payload)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n"); f.flush()
        return payload["record_hash"]
    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists(): return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    def last(self, experiment_id: str) -> dict[str, Any] | None:
        for record in reversed(self.read()):
            if record.get("experiment_id") == experiment_id: return record
        return None

__all__ = ["STATUSES", "ExperimentRecord", "JsonlExperimentLedger", "identity_hash"]
