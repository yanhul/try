"""Strict TRY execution outcome taxonomy.

Agentic execution research must never turn infrastructure/provider/evaluator
failures into negative task results. Outcomes are descriptive evidence, not
promotion authority.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class OutcomeClass(str, Enum):
    TASK_SUCCESS = "TASK_SUCCESS"
    TASK_FAILURE = "TASK_FAILURE"
    EXECUTION_INFRA_FAILURE = "EXECUTION_INFRA_FAILURE"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    QUOTA_FAILURE = "QUOTA_FAILURE"
    DATA_FAILURE = "DATA_FAILURE"
    EVALUATOR_FAILURE = "EVALUATOR_FAILURE"
    UNKNOWN = "UNKNOWN"


INFRA_FAILURES = frozenset({
    OutcomeClass.EXECUTION_INFRA_FAILURE,
    OutcomeClass.PROVIDER_FAILURE,
    OutcomeClass.QUOTA_FAILURE,
    OutcomeClass.DATA_FAILURE,
    OutcomeClass.EVALUATOR_FAILURE,
})


def classify_outcome(record: Mapping[str, Any]) -> OutcomeClass:
    if not isinstance(record, Mapping):
        raise ValueError("outcome record must be a mapping")
    value = record.get("outcome_class")
    try:
        return OutcomeClass(value)
    except (TypeError, ValueError):
        raise ValueError("outcome_class is missing or unauthorized") from None


def is_infrastructure_failure(record: Mapping[str, Any]) -> bool:
    return classify_outcome(record) in INFRA_FAILURES


def require_task_evaluation(record: Mapping[str, Any]) -> OutcomeClass:
    outcome = classify_outcome(record)
    if outcome in INFRA_FAILURES or outcome is OutcomeClass.UNKNOWN:
        raise ValueError("non-task outcome cannot be promoted to task evaluation")
    return outcome
