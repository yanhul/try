from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LifecycleAction(StrEnum):
    TERMINAL = "TERMINAL"
    BLOCKED = "BLOCKED"
    CONTINUE_DURABLE_QUEUE = "CONTINUE_DURABLE_QUEUE"
    CONTINUE_RETRY = "CONTINUE_RETRY"
    CONTINUE_PROGRESS = "CONTINUE_PROGRESS"
    HOLD = "HOLD"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass(frozen=True)
class LifecycleInput:
    terminal: bool
    terminal_outcome_valid: bool
    budget_exhausted: bool
    durable_queue: bool
    retry_allowed: bool
    blocked: bool
    progress_event: bool


def decide(x: LifecycleInput) -> LifecycleAction:
    """Pure campaign transition policy; accounting counters are not liveness signals."""
    if x.blocked:
        return LifecycleAction.BLOCKED
    if x.terminal:
        return LifecycleAction.TERMINAL if x.terminal_outcome_valid else LifecycleAction.BLOCKED
    if x.durable_queue:
        return LifecycleAction.CONTINUE_DURABLE_QUEUE
    if x.budget_exhausted:
        return LifecycleAction.BUDGET_EXHAUSTED
    if x.retry_allowed:
        return LifecycleAction.CONTINUE_RETRY
    if x.progress_event:
        return LifecycleAction.CONTINUE_PROGRESS
    return LifecycleAction.HOLD
