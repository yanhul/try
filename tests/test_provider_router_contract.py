import math

from research.provider_router import ground_candidate, normalize_structural_types


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


def test_non_executable_survivor_cannot_be_grounded_as_mechanism_family():
    candidate = {
        "hypothesis_id": "discovered_primitive",
        "discovery_spec": {
            "operator": "identity",
            "left": "close",
            "threshold": 0,
            "direction": "above",
        },
    }
    selected = {"family": "china_a_share", "source_url": "https://example.test/source"}
    grounded = ground_candidate(candidate, selected)
    assert grounded["hypothesis_id"] == "discovered_primitive"
    assert "mechanism_family" not in grounded["discovery_spec"]


def test_executable_survivor_family_is_canonicalized_deterministically():
    candidate = {
        "hypothesis_id": "discovered_primitive",
        "discovery_spec": {
            "operator": "identity",
            "left": "close",
            "threshold": 0,
            "direction": "above",
        },
    }
    selected = {"family": "smc_ict", "source_url": "https://example.test/source"}
    grounded = ground_candidate(candidate, selected)
    assert grounded["hypothesis_id"] == "mechanism_family"
    assert grounded["discovery_spec"] == {
        "mechanism_family": "smc_ict",
        "threshold": 0,
        "direction": "above",
    }
