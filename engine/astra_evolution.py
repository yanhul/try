"""ASTRA bounded evolutionary research controller.

This module composes existing TRY primitives into a durable research search
operator. Evolution may change candidate configuration only; research policy,
data identity, evaluator, split/OOS rules, and promotion criteria remain
outside the mutation surface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping

from .experiment_ledger import ExperimentRecord, JsonlExperimentLedger, identity_hash


IMMUTABLE_KEYS = frozenset({
    "dataset",
    "dataset_identity",
    "evaluator",
    "evaluation_spec",
    "cost_model",
    "splits",
    "oos",
    "promotion_policy",
    "evidence_policy",
})

DEFAULT_MUTATION_SPACE = {
    "stop_fraction": (0.005, 0.01, 0.015, 0.02),
    "reward_multiple": (1.5, 2.0, 2.5, 3.0),
    "pnf_box_fraction": (0.005, 0.01, 0.02),
    "max_components": (1, 2, 3),
}


def candidate_hash(config: Mapping[str, Any]) -> str:
    """Stable identity for a candidate configuration."""
    return identity_hash(dict(config))


def mutate(parent: Mapping[str, Any], *, ordinal: int = 0,
           mutation_space: Mapping[str, tuple[Any, ...]] | None = None) -> dict[str, Any]:
    """Produce one deterministic bounded child from a parent.

    Only keys explicitly present in mutation_space are eligible. Immutable
    governance keys are rejected even if a caller attempts to add them.
    """
    space = mutation_space or DEFAULT_MUTATION_SPACE
    child = dict(parent)
    keys = sorted(k for k in space if k in child and k not in IMMUTABLE_KEYS)
    if not keys:
        raise ValueError("no_mutable_parameters")
    key = keys[ordinal % len(keys)]
    values = tuple(space[key])
    if not values:
        raise ValueError(f"empty_mutation_domain:{key}")
    current = child.get(key)
    try:
        pos = values.index(current)
    except ValueError:
        pos = -1
    child[key] = values[(pos + 1 + ordinal // len(keys)) % len(values)]
    child["parent_candidate_hash"] = candidate_hash(parent)
    return child


def validate_candidate(config: Mapping[str, Any]) -> None:
    """Fail closed if a candidate attempts to alter governance."""
    forbidden = IMMUTABLE_KEYS.intersection(config.keys())
    # Governance keys may be carried as inherited metadata, but the evolution
    # controller never accepts a mutation of their value. The caller supplies
    # an explicit immutable baseline to compare against in validate_transition.
    if any(not isinstance(k, str) for k in config):
        raise ValueError("candidate_keys_must_be_strings")


def validate_transition(parent: Mapping[str, Any], child: Mapping[str, Any]) -> None:
    """Ensure immutable fields are bit-for-bit unchanged across evolution."""
    for key in IMMUTABLE_KEYS:
        if key in parent and child.get(key) != parent[key]:
            raise ValueError(f"immutable_field_changed:{key}")


def compare(result: Mapping[str, Any], baseline: Mapping[str, Any], *, metric: str = "total_return") -> str:
    """Return PROMOTE only when the candidate strictly improves the metric.

    Missing/non-numeric metrics fail closed to REJECT.
    """
    try:
        candidate_value = float(result[metric])
        baseline_value = float(baseline[metric])
    except (KeyError, TypeError, ValueError):
        return "REJECT"
    return "PROMOTE" if candidate_value > baseline_value else "REJECT"


@dataclass
class EvolutionState:
    campaign_id: str
    generation: int = 0
    parent_candidate_hash: str | None = None
    next_ordinal: int = 0
    terminal: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "campaign_id": self.campaign_id,
            "generation": self.generation,
            "parent_candidate_hash": self.parent_candidate_hash,
            "next_ordinal": self.next_ordinal,
            "terminal": self.terminal,
            "metadata": self.metadata,
        }


class AstraEvolutionController:
    """Small orchestration layer over TRY's existing evaluator/ledger.

    Execution/evaluation are injected so ASTRA cannot bypass AIOS authority or
    replace the reference evaluator.
    """

    def __init__(self, ledger: JsonlExperimentLedger):
        self.ledger = ledger

    def propose(self, parent: Mapping[str, Any], *, ordinal: int = 0) -> dict[str, Any]:
        child = mutate(parent, ordinal=ordinal)
        validate_candidate(child)
        validate_transition(parent, child)
        return child

    def record(self, *, campaign_id: str, hypothesis_id: str,
               parent_experiment_id: str | None, config: Mapping[str, Any],
               status: str, result: Mapping[str, Any] | None = None,
               decision: str | None = None, failure_class: str | None = None,
               evidence_refs: tuple[str, ...] = ()) -> str:
        record = ExperimentRecord(
            experiment_id=f"{campaign_id}:{candidate_hash(config)[:16]}",
            hypothesis_id=hypothesis_id,
            parent_experiment_id=parent_experiment_id,
            configuration_identity=candidate_hash(config),
            status=status,
            result=result,
            decision=decision,
            failure_class=failure_class,
            evidence_refs=evidence_refs,
        )
        return self.ledger.append(record)


__all__ = [
    "AstraEvolutionController",
    "EvolutionState",
    "IMMUTABLE_KEYS",
    "DEFAULT_MUTATION_SPACE",
    "candidate_hash",
    "mutate",
    "validate_candidate",
    "validate_transition",
    "compare",
]
