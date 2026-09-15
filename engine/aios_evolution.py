"""TRY -> AIOS Evolution Plane adapter.

Trading semantics stay in TRY. This module is the only integration boundary:
TRY creates immutable candidate/evaluation payloads; AIOS owns admission and
promotion authority.

The adapter does not vendor or reimplement AIOS evolution rules. It loads
``core.evolution`` from an explicitly supplied AIOS checkout (or ``AIOS_ROOT``)
and delegates state transitions/evidence checks to that implementation.
"""
from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .strategy_spec import canonicalize, provenance, strategy_hash


@dataclass(frozen=True)
class TryEvaluation:
    """Evaluation produced by TRY's immutable research evaluator."""
    held_in: Mapping[str, Any]
    held_out: Mapping[str, Any]
    evidence_refs: tuple[str, ...]
    evaluator_digest: str

    def __post_init__(self) -> None:
        if not self.evaluator_digest.strip():
            raise ValueError("evaluator_digest must be non-empty")
        if not self.evidence_refs or any(not x.strip() for x in self.evidence_refs):
            raise ValueError("at least one evidence reference is required")


def _load_aios_evolution(aios_root: str | Path | None = None):
    root = Path(aios_root or os.environ.get("AIOS_ROOT", "")).expanduser()
    if not root:
        raise ValueError("AIOS_ROOT or aios_root is required")
    root = root.resolve()
    if not (root / "core" / "evolution.py").is_file():
        raise FileNotFoundError(f"AIOS evolution module not found under {root}")
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return importlib.import_module("core.evolution")


def make_candidate(strategy: Mapping[str, Any], *, candidate_id: str,
                   parent_id: str | None = None, artifact_ref: str | None = None,
                   lineage_depth: int = 0, aios_root: str | Path | None = None):
    """Create a DISCOVERED AIOS candidate from a canonical TRY strategy."""
    evolution = _load_aios_evolution(aios_root)
    spec = canonicalize(dict(strategy))
    artifact = artifact_ref or f"try://strategy/{strategy_hash(spec)}"
    return evolution.Candidate(
        candidate_id=candidate_id,
        parent_id=parent_id,
        artifact_ref=artifact,
        lineage_depth=lineage_depth,
        metadata={"consumer": "TRY", "strategy": spec, "provenance": provenance(spec)},
    )


def challenge(candidate, *, aios_root: str | Path | None = None):
    """Enter the AIOS CHALLENGER state before immutable evaluation."""
    evolution = _load_aios_evolution(aios_root)
    return evolution.transition(candidate, "CHALLENGER")


def evaluate(candidate, evaluation: TryEvaluation, *, aios_root: str | Path | None = None):
    """Attach TRY evaluation evidence through AIOS's evaluator-digest gate."""
    evolution = _load_aios_evolution(aios_root)
    evidence = evolution.EvaluationEvidence(
        evaluator_digest=evaluation.evaluator_digest,
        held_in=dict(evaluation.held_in),
        held_out=dict(evaluation.held_out),
        evidence_refs=tuple(evaluation.evidence_refs),
    )
    return evolution.record_evaluation(
        candidate, evidence, evaluator_digest=evaluation.evaluator_digest
    )


def admit(candidate, *, aios_root: str | Path | None = None, required_status: str = "PASS"):
    """Run AIOS's evidence-gated admission; no TRY-side self-promotion."""
    evolution = _load_aios_evolution(aios_root)
    return evolution.admit(candidate, required_status=required_status)


def promote(candidate, *, authorize, aios_root: str | Path | None = None):
    """Delegate final activation to an external AIOS authority callback."""
    evolution = _load_aios_evolution(aios_root)
    return evolution.promote(candidate, authorize=authorize)


def candidate_from_pipeline_result(result: Mapping[str, Any], *, candidate_id: str,
                                    parent_id: str | None = None, lineage_depth: int = 0,
                                    aios_root: str | Path | None = None):
    """Convert a TRY IS/validation/OOS result into an AIOS candidate/evidence pair.

    OOS is deliberately represented as held-out evidence and is never used for
    candidate selection. Admission requires the TRY validation gate and the
    AIOS held-in/held-out PASS contract.
    """
    selected = dict(result["selected_config"])
    candidate = make_candidate(
        selected,
        candidate_id=candidate_id,
        parent_id=parent_id,
        lineage_depth=lineage_depth,
        aios_root=aios_root,
    )
    validation = result["validation"]
    oos = result.get("oos")
    validation_pass = bool(validation.get("passed"))
    oos_pass = oos is not None
    evaluation = TryEvaluation(
        held_in={
            "status": "PASS" if validation_pass else "FAIL",
            "stage": "validation",
            "metrics": validation.get("result", {}).get("metrics", {}),
        },
        held_out={
            "status": "PASS" if oos_pass else "FAIL",
            "stage": "oos_locked",
            "metrics": (oos or {}).get("metrics", {}),
        },
        evidence_refs=(
            f"try://result/{result['dataset']['sha256']}",
            f"try://strategy/{strategy_hash(selected)}",
        ),
        evaluator_digest=str(result.get("evaluator_digest") or result.get("protocol", {}).get("evaluator_digest") or "TRY-PIPELINE-V1"),
    )
    return candidate, evaluation


__all__ = [
    "TryEvaluation", "make_candidate", "challenge", "evaluate", "admit",
    "promote", "candidate_from_pipeline_result",
]
