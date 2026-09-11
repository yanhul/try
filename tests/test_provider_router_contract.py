import math

from research.provider_router import normalize_structural_types


def test_numeric_string_threshold_is_losslessly_normalized():
    candidate = {"discovery_spec": {"threshold": "0.25", "window": "20"}}
    normalize_structural_types(candidate)
    assert candidate["discovery_spec"]["threshold"] == 0.25
    assert candidate["discovery_spec"]["window"] == 20


def test_non_numeric_threshold_is_not_invented():
    candidate = {"discovery_spec": {"threshold": "not-a-number"}}
    normalize_structural_types(candidate)
    assert candidate["discovery_spec"]["threshold"] == "not-a-number"


def test_non_finite_threshold_is_not_accepted_or_rewritten():
    for value in ("nan", "inf", "-inf"):
        candidate = {"discovery_spec": {"threshold": value}}
        normalize_structural_types(candidate)
        assert candidate["discovery_spec"]["threshold"] == value
        assert not math.isfinite(float(candidate["discovery_spec"]["threshold"]))


def test_missing_threshold_is_never_invented():
    candidate = {"discovery_spec": {"operator": "identity"}}
    normalize_structural_types(candidate)
    assert "threshold" not in candidate["discovery_spec"]
