from __future__ import annotations


def structural_key(candidate: dict) -> tuple:
    """Mechanism identity; tunable parameters are deliberately excluded."""
    spec = candidate.get("discovery_spec") or {}
    family = spec.get("mechanism_family") or candidate.get("mechanism_family")
    return (family, spec.get("operator"), spec.get("left"), spec.get("right"), spec.get("direction"))


def novelty_metadata(candidate: dict) -> dict:
    spec = candidate.get("discovery_spec") or {}
    key = structural_key(candidate)
    return {
        "novelty_key": "|".join("" if x is None else str(x) for x in key),
        "novelty_type": "structural_mechanism",
        "parameterization": {"window": spec.get("window"), "threshold": spec.get("threshold")},
    }


def parameter_key(candidate: dict) -> tuple:
    """Parameter identity for local optimization after structural discovery."""
    spec = candidate.get("discovery_spec") or {}
    return structural_key(candidate) + (spec.get("window"), spec.get("threshold"))
