"""Authoritative durable lifecycle for Research/ASTRA integration.

This module owns lifecycle state only. ASTRA can propose mutations, but cannot
advance a candidate to promotion. Every transition is append-only and bound to
candidate/work/attempt identity so restart can reconcile unfinished work.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

STATES = (
    "DISCOVERED", "CLAIMED", "TRANSLATING", "EVALUATING", "VALIDATING",
    "OOS_ELIGIBLE", "OOS_EXECUTING", "EVIDENCE_COMPLETE", "DECISION_PENDING",
    "PROMOTED", "REJECTED", "EXHAUSTED", "WAITING", "UNKNOWN",
)

TERMINAL = frozenset({"PROMOTED", "REJECTED", "EXHAUSTED"})
ATTEMPT_STATES = frozenset({"CREATED", "RUNNING", "SUCCEEDED", "RETRYABLE_FAILURE", "PERMANENT_FAILURE", "UNKNOWN"})

TRANSITIONS = {
    "DISCOVERED": {"CLAIMED", "REJECTED", "EXHAUSTED"},
    "CLAIMED": {"TRANSLATING", "WAITING", "UNKNOWN", "REJECTED"},
    "TRANSLATING": {"EVALUATING", "WAITING", "UNKNOWN", "REJECTED"},
    "EVALUATING": {"VALIDATING", "WAITING", "UNKNOWN", "REJECTED"},
    "VALIDATING": {"OOS_ELIGIBLE", "REJECTED", "EXHAUSTED", "WAITING", "UNKNOWN"},
    "OOS_ELIGIBLE": {"OOS_EXECUTING", "REJECTED", "WAITING", "UNKNOWN"},
    "OOS_EXECUTING": {"EVIDENCE_COMPLETE", "REJECTED", "WAITING", "UNKNOWN"},
    "EVIDENCE_COMPLETE": {"DECISION_PENDING", "REJECTED", "UNKNOWN"},
    "DECISION_PENDING": {"PROMOTED", "REJECTED"},
    "WAITING": {"CLAIMED", "TRANSLATING", "EVALUATING", "OOS_EXECUTING", "UNKNOWN", "REJECTED"},
    "UNKNOWN": {"CLAIMED", "TRANSLATING", "EVALUATING", "OOS_EXECUTING", "REJECTED", "WAITING"},
    "PROMOTED": set(), "REJECTED": set(), "EXHAUSTED": set(),
}


@dataclass(frozen=True)
class LifecycleEvent:
    campaign_id: str
    candidate_id: str
    research_work_id: str
    attempt_id: str | None
    from_state: str | None
    to_state: str
    reason_code: str
    evidence_refs: tuple[str, ...] = ()
    parent_id: str | None = None
    decision_id: str | None = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if self.to_state not in STATES:
            raise ValueError(f"invalid_lifecycle_state:{self.to_state}")
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc).isoformat())

    @property
    def event_id(self) -> str:
        payload = asdict(self)
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class LifecycleStore:
    """Append-only lifecycle event store with fail-closed transitions."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def current(self, candidate_id: str) -> str | None:
        state = None
        for event in self.read():
            if event.get("candidate_id") == candidate_id:
                state = event.get("to_state")
        return state

    def transition(self, event: LifecycleEvent) -> str:
        current = self.current(event.candidate_id)
        if current != event.from_state:
            raise ValueError(f"lifecycle_state_conflict:{current!r}->{event.to_state!r}")
        if event.from_state is not None and event.to_state not in TRANSITIONS.get(event.from_state, set()):
            raise ValueError(f"invalid_lifecycle_transition:{event.from_state}->{event.to_state}")
        payload = asdict(event)
        payload["evidence_refs"] = list(event.evidence_refs)
        payload["event_id"] = event.event_id
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
        return event.event_id

    def ensure_discovered(self, campaign_id: str, candidate_id: str, research_work_id: str, *, parent_id: str | None = None) -> str:
        if self.current(candidate_id) is None:
            return self.transition(LifecycleEvent(campaign_id, candidate_id, research_work_id, None, None, "DISCOVERED", "CANDIDATE_DISCOVERED", parent_id=parent_id))
        return self.current(candidate_id) or "DISCOVERED"


def new_attempt_id(candidate_id: str, attempt_no: int) -> str:
    return hashlib.sha256(f"{candidate_id}:{attempt_no}".encode()).hexdigest()


__all__ = ["ATTEMPT_STATES", "LifecycleEvent", "LifecycleStore", "STATES", "TERMINAL", "TRANSITIONS", "new_attempt_id"]
