"""Durable ASTRA search loop: bounded mutation, evidence, ranking, resume."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .astra_evaluator import build_evaluator
from .evolution_controller import Candidate, Evaluation, EvolutionController
from .experiment_ledger import JsonlExperimentLedger

@dataclass(frozen=True)
class CampaignState:
    generation: int
    parent: dict[str, Any]
    baseline_score: float | None
    terminal: bool = False
    failure_class: str | None = None
    parent_evidence_id: str | None = None
    promotion_decision: str | None = None

def _save(path: Path, state: CampaignState) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"generation": state.generation, "parent": state.parent, "baseline_score": state.baseline_score, "terminal": state.terminal, "failure_class": state.failure_class, "parent_evidence_id": state.parent_evidence_id, "promotion_decision": state.promotion_decision}, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

def load_state(path: str | Path) -> CampaignState | None:
    p = Path(path)
    if not p.exists(): return None
    raw = json.loads(p.read_text(encoding="utf-8"))
    return CampaignState(int(raw["generation"]), dict(raw["parent"]), raw.get("baseline_score"), bool(raw.get("terminal", False)), raw.get("failure_class"), raw.get("parent_evidence_id"), raw.get("promotion_decision"))

def _unique_mutations(items: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    seen = set(); out = []
    for field, value in items:
        key = (field, json.dumps(value, sort_keys=True, separators=(",", ":")))
        if key not in seen: seen.add(key); out.append((field, value))
    return out

def _mutations(parent: Candidate, generation: int) -> list[tuple[str, Any]]:
    """Coarse-to-fine coordinate search with a stable positive reward frontier."""
    c = parent.config; stop = max(1e-6, float(c.get("stop_fraction", 0.01))); rr = max(0.25, float(c.get("reward_multiple", 2.0))); pnf = max(1e-6, float(c.get("pnf_box_fraction", 0.01)))
    phase = generation % 3
    if phase == 0: stop_scales, rr_delta, pnf_scales = (0.60, 0.80, 1.25, 1.60), (0.5, -0.5, -1.0), (0.60, 0.80, 1.25, 1.60)
    elif phase == 1: stop_scales, rr_delta, pnf_scales = (0.85, 0.925, 1.08, 1.175), (0.5, -0.1, -0.25, 0.1), (0.85, 0.925, 1.08, 1.175)
    else: stop_scales, rr_delta, pnf_scales = (0.95, 1.05), (0.5, -0.1, 0.1), (0.95, 1.05)
    items = [("reward_multiple", round(max(0.25, rr + x), 8)) for x in rr_delta]
    items += [("stop_fraction", round(stop * x, 8)) for x in stop_scales]
    items += [("pnf_box_fraction", round(pnf * x, 8)) for x in pnf_scales]
    return _unique_mutations(items)

def _last_evaluation(ledger: JsonlExperimentLedger, candidate_id: str) -> dict[str, Any] | None:
    terminal = {"SUCCEEDED", "REJECTED", "INVALID", "FAILED", "CRASHED"}; found = None
    for record in ledger.read():
        if record.get("experiment_id") == candidate_id and record.get("status") in terminal: found = record
    return found

def _parent_failure(ledger: JsonlExperimentLedger, parent: Candidate) -> str | None:
    record = _last_evaluation(ledger, parent.id); value = (record or {}).get("failure_class")
    return str(value) if value else None

def _evidence_id(record: dict[str, Any] | None) -> str | None:
    if not record: return None
    return str(record.get("event_id") or record.get("id") or record.get("experiment_id") or "") or None

def _verified_parent(ledger: JsonlExperimentLedger, state: CampaignState) -> tuple[Candidate, dict[str, Any]]:
    parent = Candidate(state.parent); record = _last_evaluation(ledger, parent.id)
    if record is None: raise RuntimeError(f"missing terminal evidence for parent {parent.id}")
    actual = _evidence_id(record)
    if state.parent_evidence_id and actual != state.parent_evidence_id: raise RuntimeError(f"parent evidence mismatch: expected {state.parent_evidence_id}, got {actual}")
    if str(record.get("status")) not in {"SUCCEEDED", "REJECTED"}: raise RuntimeError(f"parent lacks usable terminal evidence: {record.get('status')}")
    return parent, record

def run_campaign(data_path: str | Path, ledger_path: str | Path, state_path: str | Path, *, max_generations: int = 100, generation_limit: int = 6) -> CampaignState:
    if max_generations < 1 or generation_limit < 1: raise ValueError("campaign limits must be positive")
    ledger = JsonlExperimentLedger(ledger_path); controller = EvolutionController(ledger, build_evaluator(data_path)); state = load_state(state_path)
    if state is None:
        parent = Candidate({"hypothesis_id": "baseline", "stop_fraction": 0.01, "reward_multiple": 2.0, "pnf_box_fraction": 0.01})
        baseline = controller.evaluate(parent, hypothesis_id="astra"); record = _last_evaluation(ledger, parent.id)
        state = CampaignState(0, dict(parent.config), baseline.score, False, baseline.failure_class, _evidence_id(record), "PROMOTE" if baseline.status == "SUCCEEDED" else "REJECT"); _save(Path(state_path), state)
    while state.generation < max_generations:
        parent, evidence = _verified_parent(ledger, state)
        baseline_score = (evidence.get("result") or {}).get("score", state.baseline_score)
        baseline = Evaluation(str(evidence.get("status")), baseline_score, dict(evidence.get("result") or {}), evidence.get("failure_class"))
        failure_class = state.failure_class or _parent_failure(ledger, parent)
        best = controller.run_generation(parent, _mutations(parent, state.generation), baseline, limit=generation_limit, hypothesis_id="astra", failure_class=failure_class)
        best_record = _last_evaluation(ledger, best.id)
        if best.id != parent.id and best_record is None: raise RuntimeError(f"missing terminal evidence for selected candidate {best.id}")
        candidate_score = (best_record.get("result") or {}).get("score") if best_record else None
        promote = best.id != parent.id and best_record and best_record.get("status") == "SUCCEEDED" and candidate_score is not None and baseline_score is not None and float(candidate_score) > float(baseline_score)
        next_parent = best if promote else parent; score = float(candidate_score) if promote else baseline_score
        next_record = _last_evaluation(ledger, next_parent.id)
        state = CampaignState(state.generation + 1, dict(next_parent.config), score, state.generation + 1 >= max_generations, _parent_failure(ledger, next_parent), _evidence_id(next_record), "PROMOTE" if promote else "REJECT"); _save(Path(state_path), state)
    return state

__all__ = ["CampaignState", "load_state", "run_campaign"]
