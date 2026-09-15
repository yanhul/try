"""Bounded evolutionary controller for ASTRA research campaigns.

Search state is mutable; research contract, evaluator, dataset, OOS lock,
and promotion policy remain outside this controller.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Mapping, Sequence

from .experiment_ledger import ExperimentRecord, JsonlExperimentLedger

IMMUTABLE_KEYS = frozenset({
    "dataset", "dataset_identity", "evaluator", "evaluation_spec",
    "cost_model", "oos_policy", "promotion_policy", "evidence_policy",
})
ALLOWED_MUTATIONS = frozenset({
    "stop_fraction", "reward_multiple", "pnf_box_fraction",
    "candidate_family", "candidate_spec",
})
EVALUATION_STATUSES = frozenset({"SUCCEEDED", "REJECTED", "INVALID", "FAILED", "CRASHED"})


def _reject_immutable(value: Any, path: str = "candidate") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in IMMUTABLE_KEYS:
                raise ValueError(f"immutable_candidate_fields:{path}.{key}")
            _reject_immutable(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_immutable(nested, f"{path}[{index}]")


def canonical_candidate(config: Mapping[str, Any]) -> dict[str, Any]:
    _reject_immutable(config)
    return json.loads(json.dumps(dict(config), sort_keys=True, ensure_ascii=False))


def candidate_id(config: Mapping[str, Any]) -> str:
    payload = json.dumps(canonical_candidate(config), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def mutate(parent: Mapping[str, Any], field: str, value: Any) -> dict[str, Any]:
    if field not in ALLOWED_MUTATIONS:
        raise ValueError(f"mutation_not_allowed:{field}")
    child = canonical_candidate(parent)
    child[field] = value
    return canonical_candidate(child)


@dataclass(frozen=True)
class Candidate:
    config: Mapping[str, Any]
    parent_id: str | None = None

    @property
    def id(self) -> str:
        return candidate_id(self.config)


@dataclass(frozen=True)
class Evaluation:
    status: str
    score: float | None
    result: Mapping[str, Any]
    failure_class: str | None = None


class EvolutionController:
    """Generate, evaluate and make evidence-backed search decisions."""

    def __init__(self, ledger: JsonlExperimentLedger, evaluator: Callable[[Mapping[str, Any]], Evaluation]):
        self.ledger = ledger
        self.evaluator = evaluator

    def propose(self, parent: Candidate, mutations: Sequence[tuple[str, Any]], limit: int = 8) -> list[Candidate]:
        if limit < 1:
            raise ValueError("limit must be positive")
        seen: set[str] = set()
        out: list[Candidate] = []
        for field, value in mutations:
            child = Candidate(mutate(parent.config, field, value), parent.id)
            if child.id == parent.id or child.id in seen:
                continue
            seen.add(child.id)
            out.append(child)
            if len(out) >= limit:
                break
        return out

    def _terminal_ids(self) -> set[str]:
        terminal = {"SUCCEEDED", "REJECTED", "INVALID", "FAILED", "CRASHED", "PROMOTED"}
        return {
            record["experiment_id"]
            for record in self.ledger.read()
            if record.get("status") in terminal and record.get("experiment_id")
        }

    def evaluate(self, candidate: Candidate, hypothesis_id: str = "astra") -> Evaluation:
        exp_id = candidate.id
        if exp_id in self._terminal_ids():
            last = self.ledger.last(exp_id)
            if last and last.get("status") == "PROMOTED":
                return Evaluation("SUCCEEDED", last.get("result", {}).get("score"), last.get("result", {}))
            if last and last.get("status") in EVALUATION_STATUSES:
                result = last.get("result") or {}
                return Evaluation(last["status"], result.get("score"), result, last.get("failure_class"))
        self.ledger.append(ExperimentRecord(
            experiment_id=exp_id, hypothesis_id=hypothesis_id, status="PROPOSED",
            parent_experiment_id=candidate.parent_id, configuration_identity=exp_id,
            result={"candidate": candidate.config},
        ))
        try:
            evaluation = self.evaluator(candidate.config)
        except Exception as exc:
            evaluation = Evaluation("CRASHED", None, {"error": str(exc)}, "EXECUTION_EXCEPTION")
        if evaluation.status not in EVALUATION_STATUSES:
            raise ValueError(f"invalid_evaluation_status:{evaluation.status}")
        self.ledger.append(ExperimentRecord(
            experiment_id=exp_id, hypothesis_id=hypothesis_id, status=evaluation.status,
            parent_experiment_id=candidate.parent_id, configuration_identity=exp_id,
            result=dict(evaluation.result), failure_class=evaluation.failure_class,
            decision=None,
        ))
        return evaluation

    def decide(self, candidate: Candidate, evaluation: Evaluation, baseline: Evaluation,
               hypothesis_id: str = "astra") -> str:
        decision = self.compare(evaluation, baseline)
        self.ledger.append(ExperimentRecord(
            experiment_id=candidate.id, hypothesis_id=hypothesis_id,
            status="PROMOTED" if decision == "PROMOTE" else "REJECTED",
            parent_experiment_id=candidate.parent_id, configuration_identity=candidate.id,
            result={"score": evaluation.score, "baseline_score": baseline.score},
            decision=decision,
        ))
        return decision

    def run_generation(self, parent: Candidate, mutations: Sequence[tuple[str, Any]], baseline: Evaluation,
                       limit: int = 8, hypothesis_id: str = "astra") -> Candidate:
        """Run one bounded generation and return the best promoted child, or parent.

        Existing terminal ledger records are reused, so interruption/resume does not
        re-execute completed candidates. Promotion remains a separate decision record.
        """
        candidates = self.propose(parent, mutations, limit=limit)
        best = parent
        best_score = baseline.score if baseline.status == "SUCCEEDED" else None
        for candidate in candidates:
            evaluation = self.evaluate(candidate, hypothesis_id)
            decision = self.decide(candidate, evaluation, baseline, hypothesis_id)
            if decision == "PROMOTE" and evaluation.score is not None and (best_score is None or evaluation.score > best_score):
                best = candidate
                best_score = evaluation.score
        return best

    @staticmethod
    def compare(candidate: Evaluation, baseline: Evaluation) -> str:
        """Compare successful evaluations; promotion is a separate ledger decision."""
        if candidate.status != "SUCCEEDED" or baseline.status != "SUCCEEDED":
            return "REJECT"
        if candidate.score is None or baseline.score is None:
            return "REJECT"
        return "PROMOTE" if candidate.score > baseline.score else "REJECT"


__all__ = ["ALLOWED_MUTATIONS", "Candidate", "Evaluation", "EvolutionController",
           "candidate_id", "canonical_candidate", "mutate"]
