"""Adapter from ASTRA candidate configs to the authoritative research evaluator.

The dataset, cost model, validation policy, and OOS policy are fixed by the
adapter/evaluator boundary. Only controller-approved candidate fields are read
from the candidate configuration.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .autonomous_evaluator import (
    EVALUATION_SPEC,
    EVENT_MECHANISMS,
    HYPOTHESES,
    discovered_predicate,
    mechanism_predicate,
)
from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .hypothesis_research import evaluate_split
from .evolution_controller import Evaluation
from research.cost_model import DEFAULT_COST_MODEL


def build_evaluator(data_path: str | Path):
    """Return an ASTRA evaluator bound to one immutable dataset/policy boundary."""
    data = Path(data_path).resolve()
    bars = load_bars(data)
    splits = chronological_split(len(bars))
    validate_splits(splits, len(bars))
    cost_model = DEFAULT_COST_MODEL

    def evaluate(candidate: Mapping[str, Any]) -> Evaluation:
        hid = str(candidate.get("hypothesis_id", ""))
        spec = candidate.get("candidate_spec") or candidate.get("discovery_spec") or {}
        family = candidate.get("candidate_family")
        if hid == "discovered_primitive" or family == "discovered_primitive":
            if not isinstance(spec, dict):
                return Evaluation("INVALID", None, {"error": "UNEXECUTABLE_DISCOVERY_SPEC"}, "INVALID_SPEC")
            predicate = discovered_predicate(spec)
            universe = "all_bars"
            actual_family = "discovered_primitive"
        elif hid == "mechanism_family" or family in EVENT_MECHANISMS or family in {
            "momentum_trend", "mean_reversion", "wyckoff_vsa_vpa",
            "vwap_volume_profile", "regime", "point_figure", "gann_reference",
        }:
            actual_family = family or spec.get("mechanism_family")
            if not isinstance(spec, dict) or not actual_family:
                return Evaluation("INVALID", None, {"error": "UNEXECUTABLE_MECHANISM_SPEC"}, "INVALID_SPEC")
            mechanism_spec = dict(spec)
            mechanism_spec.setdefault("mechanism_family", actual_family)
            predicate = mechanism_predicate(mechanism_spec)
            universe = "reference_event_ledger" if actual_family in EVENT_MECHANISMS else "all_bars"
        elif hid in HYPOTHESES:
            predicate = HYPOTHESES[hid]
            universe = "reference_event_ledger"
            actual_family = None
        else:
            return Evaluation("INVALID", None, {"error": f"UNEXECUTABLE_HYPOTHESIS_ID:{hid}"}, "INVALID_HYPOTHESIS")

        stop = float(candidate.get("stop_fraction", EVALUATION_SPEC["stop_fraction"]))
        rr = float(candidate.get("reward_multiple", EVALUATION_SPEC["reward_multiple"]))
        pnf = float(candidate.get("pnf_box_fraction", 0.01))
        if stop <= 0 or rr <= 0 or pnf <= 0:
            return Evaluation("INVALID", None, {"error": "INVALID_RISK_OR_PNF_PARAMETER"}, "INVALID_PARAMETER")

        kwargs = {
            "candidate_universe": universe,
            "candidate_family": actual_family,
            "candidate_spec": spec,
            "pnf_box_fraction": pnf,
        }
        is_result = evaluate_split(
            bars, splits[0].start, splits[0].end, predicate, stop, rr,
            cost_model=cost_model, **kwargs,
        )
        val_result = evaluate_split(
            bars, splits[1].start, splits[1].end, predicate, stop, rr,
            cost_model=cost_model, **kwargs,
        )
        vm = val_result["metrics"]
        gross_passed = (
            vm.get("profit_factor") is not None
            and vm["profit_factor"] >= 1.0
            and vm["total_return"] >= 0.0
        )
        if not gross_passed:
            return Evaluation(
                "REJECTED", None,
                {"IS": is_result, "VALIDATION": val_result,
                 "validation_passed": False, "dataset": str(data)},
                "VALIDATION_GATE_FAILED",
            )
        score = float(vm["total_return"])
        return Evaluation(
            "SUCCEEDED", score,
            {"score": score, "IS": is_result, "VALIDATION": val_result,
             "validation_passed": True, "dataset": str(data)},
        )

    return evaluate


__all__ = ["build_evaluator"]
