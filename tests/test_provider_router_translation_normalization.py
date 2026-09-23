from research import provider_router


def test_opaque_provider_id_with_selected_mechanism_spec_is_canonicalized():
    previous = provider_router.selected_family
    try:
        provider_router.selected_family = "mean_reversion"
        candidate = {
            "hypothesis_id": "gemini_generated_hypothesis_123",
            "discovery_spec": {
                "mechanism_family": "mean_reversion",
                "threshold": 0.5,
                "direction": "above",
            },
        }
        provider_router.normalize_hypothesis_id(candidate)
        assert candidate["hypothesis_id"] == "mechanism_family"
    finally:
        provider_router.selected_family = previous



def test_selected_family_with_primitive_fields_is_canonicalized_as_discovered_primitive():
    previous = provider_router.selected_family
    try:
        provider_router.selected_family = "momentum_trend"
        candidate = {
            "hypothesis_id": "gemini_generated_hypothesis_primitive",
            "discovery_spec": {
                "mechanism_family": "momentum_trend",
                "operator": "difference",
                "left": "high",
                "right": "low",
                "threshold": 0.5,
                "direction": "above",
            },
        }
        provider_router.normalize_hypothesis_id(candidate)
        assert candidate["hypothesis_id"] == "discovered_primitive"
    finally:
        provider_router.selected_family = previous


def test_selected_family_with_malformed_primitive_fields_fails_closed():
    previous = provider_router.selected_family
    try:
        provider_router.selected_family = "momentum_trend"
        candidate = {
            "hypothesis_id": "mechanism_family",
            "discovery_spec": {
                "mechanism_family": "momentum_trend",
                "operator": "zscore",
                "left": "volume",
                "threshold": 3.0,
                "window": 24,
                "direction": "above",
            },
        }
        provider_router.normalize_hypothesis_id(candidate)
        assert candidate["hypothesis_id"] == "discovered_primitive"
        assert candidate["discovery_spec"]["operator"] == "zscore"
    finally:
        provider_router.selected_family = previous


def test_selected_family_with_partial_primitive_fields_does_not_downgrade_to_family():
    previous = provider_router.selected_family
    try:
        provider_router.selected_family = "momentum_trend"
        candidate = {
            "hypothesis_id": "mechanism_family",
            "discovery_spec": {
                "mechanism_family": "momentum_trend",
                "operator": "zscore",
                "threshold": 3.0,
                "window": 24,
                "direction": "above",
            },
        }
        provider_router.normalize_hypothesis_id(candidate)
        assert candidate["hypothesis_id"] == "invalid_discovered_primitive"
    finally:
        provider_router.selected_family = previous

def test_opaque_provider_id_with_primitive_spec_is_canonicalized():
    previous = provider_router.selected_family
    try:
        provider_router.selected_family = "momentum_trend"
        candidate = {
            "hypothesis_id": "gemini_generated_hypothesis_456",
            "discovery_spec": {
                "operator": "zscore",
                "left": "close",
                "window": 20,
                "threshold": 1.5,
                "direction": "above",
            },
        }
        provider_router.normalize_hypothesis_id(candidate)
        assert candidate["hypothesis_id"] == "discovered_primitive"
    finally:
        provider_router.selected_family = previous


def test_mismatched_explicit_mechanism_family_is_not_retargeted():
    previous = provider_router.selected_family
    try:
        provider_router.selected_family = "mean_reversion"
        candidate = {
            "hypothesis_id": "gemini_generated_hypothesis_789",
            "discovery_spec": {
                "mechanism_family": "momentum_trend",
                "threshold": 0.5,
                "direction": "above",
            },
        }
        provider_router.normalize_hypothesis_id(candidate)
        assert candidate["hypothesis_id"] == "gemini_generated_hypothesis_789"
        assert candidate["discovery_spec"]["mechanism_family"] == "momentum_trend"
    finally:
        provider_router.selected_family = previous


def test_composite_provider_id_is_canonicalized():
    previous = provider_router.selected_family
    try:
        provider_router.selected_family = "mean_reversion"
        candidate = {
            "hypothesis_id": "gemini_composite_candidate",
            "discovery_spec": {
                "mechanism_family": "mean_reversion",
                "combine": "and",
                "terms": [
                    {"operator": "zscore", "left": "close", "window": 20, "threshold": 1.5, "direction": "above"},
                    {"operator": "difference", "left": "close", "right": "vwap_distance", "threshold": 0.5, "direction": "above"},
                ],
            },
        }
        provider_router.normalize_hypothesis_id(candidate)
        assert candidate["hypothesis_id"] == "composite_primitive"
    finally:
        provider_router.selected_family = previous


def test_composite_validation_is_fail_closed_and_hashes():
    from research.autonomous_hypothesis import validate_candidate
    candidate = {
        "bc": 10,
        "parent_bc": 9,
        "hypothesis_id": "composite_primitive",
        "discovery_spec": {
            "mechanism_family": "mean_reversion",
            "combine": "or",
            "terms": [
                {"operator": "zscore", "left": "close", "window": 20, "threshold": 1.5, "direction": "above"},
                {"operator": "ratio", "left": "close", "right": "vwap_distance", "threshold": 1.01, "direction": "below"},
            ],
        },
        "conceptual_change": "bounded two-term composition",
        "evidence_sources": ["https://example.invalid/source"],
        "rationale": "test",
        "is_testable": True,
        "oos_selection_used": False,
    }
    ok, reason = validate_candidate(candidate, 10, 9)
    assert ok, reason
    assert candidate["candidate_hash"]
    bad = dict(candidate)
    bad["discovery_spec"] = dict(candidate["discovery_spec"])
    bad["discovery_spec"]["terms"] = candidate["discovery_spec"]["terms"][:1]
    bad.pop("candidate_hash", None)
    ok, reason = validate_candidate(bad, 10, 9)
    assert not ok
    assert reason == "composite_requires_two_terms"
