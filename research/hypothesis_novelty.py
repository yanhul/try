from __future__ import annotations

from copy import deepcopy

PARAMETER_WINDOWS = (3, 5, 10, 20, 50, 100)
PARAMETER_THRESHOLDS = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0)

# Thresholds are expressed in the native scale of the family feature.  The
# previous global 0.5..3.0 range was invalid for return-like features such as
# momentum_trend and vwap distance, causing repeated zero-signal candidates.
FAMILY_PARAMETER_THRESHOLDS = {
    "momentum_trend": (0.0, 0.001, 0.0025, 0.005, 0.01, 0.02, 0.05),
    "mean_reversion": (0.0, 0.25, 0.5, 1.0, 1.5, 2.0),
    "smc_ict": (0.0, 0.0005, 0.001, 0.0025, 0.005, 0.01),
    "fvg_imbalance": (0.0, 0.0005, 0.001, 0.0025, 0.005, 0.01),
    "wyckoff_vsa_vpa": (0.5, 0.6, 0.7, 0.8, 0.9),
    "vwap_volume_profile": (0.0, 0.001, 0.0025, 0.005, 0.01, 0.02),
    "regime": (0.0, 0.5, 1.0),
    "point_figure": (0.0, 0.5, 1.0),
    "gann_reference": (0.0, 0.0005, 0.001, 0.0025, 0.005, 0.01),
}


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


def parameter_variants(candidate: dict, limit: int = 12) -> list[dict]:
    """Bounded same-mechanism IS/validation parameter search; never an OOS selector."""
    spec = candidate.get("discovery_spec") or {}
    if not isinstance(spec, dict) or limit <= 0:
        return []
    base = deepcopy(candidate)
    variants = []
    seen = {parameter_key(base)}
    current_window = spec.get("window")
    current_threshold = spec.get("threshold")
    windows = PARAMETER_WINDOWS if "window" in spec else (None,)
    family = spec.get("mechanism_family")
    thresholds = FAMILY_PARAMETER_THRESHOLDS.get(family, PARAMETER_THRESHOLDS)
    ordered_thresholds = [current_threshold] + [x for x in thresholds if x != current_threshold]
    ordered_windows = [current_window] + [x for x in windows if x != current_window]
    for window in ordered_windows:
        for threshold in ordered_thresholds:
            c = deepcopy(base)
            cs = c.setdefault("discovery_spec", {})
            if window is not None:
                cs["window"] = window
            cs["threshold"] = threshold
            key = parameter_key(c)
            if key in seen:
                continue
            seen.add(key)
            c["search_phase"] = "PARAMETER_OPTIMIZATION"
            c["optimization_parent_hypothesis_id"] = candidate.get("hypothesis_id")
            # Rebuild derived novelty metadata after changing parameters.  Never
            # carry stale window/threshold values from the parent artifact.
            c.pop("candidate_hash", None)
            c.update(novelty_metadata(c))
            variants.append(c)
            if len(variants) >= limit:
                return variants
    return variants
