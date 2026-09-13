"""Structural novelty rules for autonomous research hypotheses."""
from __future__ import annotations


def structural_key(candidate: dict) -> tuple:
    """Return the mechanism identity, excluding tunable parameters."""
    spec = candidate.get("discovery_spec") or {}
    family = spec.get("mechanism_family") or candidate.get("mechanism_family")
    return (
        family,
        spec.get("operator"),
        spec.get("left"),
        spec.get("right"),
        spec.get("direction"),
    )


def novelty_metadata(candidate: dict) -> dict:
    """Describe what is genuinely new without treating threshold/window as novelty."""
    spec = candidate.get("discovery_spec") or {}
    key = structural_key(candidate)
    return {
        "novelty_key": "|".join("" if x is None else str(x) for x in key),
        "novelty_type": "structural_mechanism",
        "parameterization": {
            "window": spec.get("window"),
            "threshold": spec.get("threshold"),
        },
    }
