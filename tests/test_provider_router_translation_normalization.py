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
