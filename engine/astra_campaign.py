"""Durable ASTRA campaign loop: evolve, evaluate, promote, persist, resume."""
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


def _save(path: Path, state: CampaignState) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({
        "generation": state.generation,
        "parent": state.parent,
        "baseline_score": state.baseline_score,
        "terminal": state.terminal,
    }, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_state(path: str | Path) -> CampaignState | None:
    p = Path(path)
    if not p.exists():
        return None
    raw = json.loads(p.read_text(encoding="utf-8"))
    return CampaignState(
        generation=int(raw["generation"]),
        parent=dict(raw["parent"]),
        baseline_score=raw.get("baseline_score"),
        terminal=bool(raw.get("terminal", False)),
    )


def _mutations(parent: Candidate) -> list[tuple[str, Any]]:
    """Deterministic bounded neighborhood; policy/evaluator fields never mutate."""
    c = parent.config
    stop = float(c.get("stop_fraction", 0.01))
    rr = float(c.get("reward_multiple", 2.0))
    pnf = float(c.get("pnf_box_fraction", 0.01))
    return [
        ("stop_fraction", round(stop * 0.8, 8)),
        ("stop_fraction", round(stop * 1.25, 8)),
        ("reward_multiple", round(rr - 0.5, 8)),
        ("reward_multiple", round(rr + 0.5, 8)),
        ("pnf_box_fraction", round(pnf * 0.8, 8)),
        ("pnf_box_fraction", round(pnf * 1.25, 8)),
    ]


def run_campaign(
    data_path: str | Path,
    ledger_path: str | Path,
    state_path: str | Path,
    *,
    max_generations: int = 100,
    generation_limit: int = 6,
) -> CampaignState:
    """Run/resume bounded generations until the explicit campaign budget is exhausted."""
    if max_generations < 1 or generation_limit < 1:
        raise ValueError("campaign limits must be positive")

    ledger = JsonlExperimentLedger(ledger_path)
    controller = EvolutionController(ledger, build_evaluator(data_path))
    state = load_state(state_path)
    if state is None:
        parent = Candidate({
            "hypothesis_id": "baseline",
            "stop_fraction": 0.01,
            "reward_multiple": 2.0,
            "pnf_box_fraction": 0.01,
        })
        baseline = controller.evaluate(parent, hypothesis_id="astra")
        state = CampaignState(0, dict(parent.config), baseline.score, False)
        _save(Path(state_path), state)

    # `terminal` records that the previous invocation exhausted its own
    # generation budget; it is not a reason to discard a durable resumable
    # search state when a later invocation explicitly raises that budget.
    while state.generation < max_generations:
        parent = Candidate(state.parent)
        baseline = Evaluation("SUCCEEDED", state.baseline_score, {"score": state.baseline_score})
        best = controller.run_generation(
            parent, _mutations(parent), baseline,
            limit=generation_limit, hypothesis_id="astra",
        )
        score = state.baseline_score
        if best.id != parent.id:
            promoted = controller.ledger.last(best.id)
            if promoted:
                score = (promoted.get("result") or {}).get("score", score)
        state = CampaignState(
            generation=state.generation + 1,
            parent=dict(best.config),
            baseline_score=score,
            terminal=(state.generation + 1 >= max_generations),
        )
        _save(Path(state_path), state)
    return state


__all__ = ["CampaignState", "load_state", "run_campaign"]
