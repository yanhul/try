import math

import pytest

from research.provider_router import ground_candidate, normalize_structural_types, normalize_hypothesis_id, request_candidate
from research import provider_router
from research.autonomous_hypothesis import EXECUTABLE_MECHANISM_FAMILIES, validate_candidate
from research.btc_translation_policy import btc_translation_status, eligible_survivors


def test_numeric_string_threshold_is_losslessly_normalized():
    candidate = {"discovery_spec": {"threshold": "0.25", "window": "20"}}
    normalize_structural_types(candidate)
    assert candidate["discovery_spec"]["threshold"] == 0.25
    assert candidate["discovery_spec"]["window"] == 20


def test_numeric_threshold_alias_is_losslessly_canonicalized():
    candidate = {"discovery_spec": {"numeric_finite_threshold": "0.25"}}
    normalize_structural_types(candidate)
    assert candidate["discovery_spec"]["threshold"] == 0.25
    assert "numeric_finite_threshold" in candidate["discovery_spec"]


def test_numeric_threshold_alias_integer_is_canonicalized():
    candidate = {"discovery_spec": {"numeric_finite_threshold": 1}}
    normalize_structural_types(candidate)
    assert candidate["discovery_spec"]["threshold"] == 1


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


def test_non_finite_threshold_alias_is_not_canonicalized():
    for value in (float("nan"), float("inf"), float("-inf")):
        candidate = {"discovery_spec": {"numeric_finite_threshold": value}}
        normalize_structural_types(candidate)
        assert "threshold" not in candidate["discovery_spec"]


def test_missing_threshold_is_never_invented():
    candidate = {"discovery_spec": {"operator": "identity"}}
    normalize_structural_types(candidate)
    assert "threshold" not in candidate["discovery_spec"]


def test_provider_rejects_top_level_array_without_attribute_error(monkeypatch):
    monkeypatch.setattr(provider_router, "call", lambda prompt: "[]")
    monkeypatch.setattr(provider_router, "deterministic_candidate", lambda forbidden: {"hypothesis_id": "discovered_primitive", "discovery_spec": {"operator": "identity", "left": "close", "threshold": 0, "direction": "above"}})
    result = request_candidate("test", set())
    assert result["hypothesis_id"] == "discovered_primitive"


def test_exact_selected_family_id_is_canonicalized_only():
    previous = provider_router.selected_family
    try:
        provider_router.selected_family = "smc_ict"
        candidate = {"hypothesis_id": "smc_ict", "discovery_spec": {"threshold": 0.5, "direction": "above"}}
        normalize_hypothesis_id(candidate)
        assert candidate["hypothesis_id"] == "mechanism_family"
        assert candidate["discovery_spec"]["mechanism_family"] == "smc_ict"
        assert candidate["discovery_spec"]["threshold"] == 0.5
    finally:
        provider_router.selected_family = previous


def test_opaque_provider_id_with_primitive_spec_is_canonicalized():
    previous = provider_router.selected_family
    try:
        provider_router.selected_family = "smc_ict"
        candidate = {"hypothesis_id": "mean_reversion", "discovery_spec": {"mechanism_family": "smc_ict", "operator": "difference", "left": "high", "right": "low", "threshold": 0.5, "direction": "above"}}
        normalize_hypothesis_id(candidate)
        assert candidate["hypothesis_id"] == "mechanism_family"
    finally:
        provider_router.selected_family = previous


def test_non_directional_mechanism_family_is_not_executable():
    candidate = {
        "bc": 168,
        "parent_bc": 167,
        "hypothesis_id": "mechanism_family",
        "conceptual_change": "test volatility",
        "evidence_sources": ["https://example.test/source"],
        "rationale": "test",
        "is_testable": True,
        "oos_selection_used": False,
        "discovery_spec": {"mechanism_family": "volatility", "threshold": 0.1, "direction": "above"},
    }
    ok, reason = validate_candidate(candidate, 168, 167)
    assert not ok
    assert reason == "non_directional_mechanism_family"
    assert "volatility" not in EXECUTABLE_MECHANISM_FAMILIES
    assert "seasonality" not in EXECUTABLE_MECHANISM_FAMILIES


def test_non_executable_survivor_cannot_be_grounded():
    candidate = {"hypothesis_id": "discovered_primitive", "discovery_spec": {"operator": "identity", "left": "close", "threshold": 0, "direction": "above"}}
    selected = {"family": "china_a_share", "source_url": "https://example.test/source"}
    with pytest.raises(ValueError, match="non_executable_source_reached_grounding"):
        ground_candidate(candidate, selected)


def test_executable_survivor_translation_is_preserved():
    candidate = {"hypothesis_id": "discovered_primitive", "discovery_spec": {"operator": "zscore", "left": "close", "window": 20, "threshold": 1.5, "direction": "above"}}
    selected = {"family": "mean_reversion", "source_url": "https://example.test/source"}
    grounded = ground_candidate(candidate, selected)
    assert grounded["hypothesis_id"] == "discovered_primitive"
    assert grounded["discovery_spec"]["operator"] == "zscore"
    assert grounded["discovery_spec"]["threshold"] == 1.5
    assert grounded["evidence_sources"] == ["https://example.test/source"]


def test_mechanism_family_must_match_selected_survivor():
    candidate = {"hypothesis_id": "mechanism_family", "discovery_spec": {"mechanism_family": "smc_ict", "threshold": 0, "direction": "above"}}
    selected = {"family": "mean_reversion", "source_url": "https://example.test/source"}
    with pytest.raises(ValueError, match="selected_family_mismatch"):
        ground_candidate(candidate, selected)


def test_cross_sectional_source_is_not_btc_translatable():
    ok, reason = btc_translation_status({"family": "cross_sectional", "market": None, "title": "factor portfolio", "description": "cross-sectional alpha portfolio"})
    assert not ok
    assert reason.startswith("non_portable_family:")


def test_order_book_data_cannot_be_silently_translated_to_ohlcv():
    ok, reason = btc_translation_status({"family": "smc_ict", "market": None, "title": "order book", "description": "Level-2 order book liquidity strategy"})
    assert not ok
    assert reason.startswith("requires_unavailable_data:")


def test_crypto_mean_reversion_is_btc_translatable():
    ok, reason = btc_translation_status({"family": "mean_reversion", "market": None, "title": "crypto mean reversion", "description": "crypto z-score mean reversion strategy"})
    assert ok
    assert reason == "portable_to_btc_ohlcv"


def test_non_crypto_market_is_rejected_even_when_family_is_portable():
    ok, reason = btc_translation_status({"family": "momentum_trend", "market": "CN_A_SHARE", "title": "momentum", "description": "price momentum"})
    assert not ok
    assert reason == "single_asset_incompatible:CN_A_SHARE"


def test_filter_removes_incompatible_sources_before_selection():
    eligible, rejected = eligible_survivors([
        {"family": "smc_ict", "market": None, "title": "BTC/ETH ICT", "description": "crypto liquidity sweep MSS FVG", "source_url": "https://example.test/a"},
        {"family": "china_a_share", "market": "CN_A_SHARE", "title": "A-share", "description": "China stock portfolio", "source_url": "https://example.test/b"},
    ])
    assert [x["family"] for x in eligible] == ["smc_ict"]
    assert [x["family"] for x in rejected] == ["china_a_share"]


def test_duplicate_retry_prompt_is_augmented_without_truncating_frontier(monkeypatch):
    prompts = []
    candidate = {
        "hypothesis_id": "discovered_primitive",
        "discovery_spec": {"operator": "identity", "left": "close", "threshold": 0, "direction": "above"},
    }
    monkeypatch.setattr(provider_router, "call", lambda prompt: prompts.append(prompt) or __import__("json").dumps(candidate))
    monkeypatch.setattr(provider_router, "validate_candidate", lambda c, bc, parent: (False, "duplicate_structural_mechanism"))
    forbidden = {("old_family", "operator", "left", "right", "above")}
    previous_family = provider_router.selected_family
    try:
        provider_router.selected_family = "momentum_trend"
        monkeypatch.setattr(provider_router, "deterministic_candidate", lambda forbidden: {"hypothesis_id": "discovered_primitive", "discovery_spec": {"operator": "delta", "left": "close", "window": 3, "threshold": 0, "direction": "above"}})
        result = request_candidate("BASE", forbidden)
        assert result["discovery_spec"]["operator"] == "delta"
    finally:
        provider_router.selected_family = previous_family
    assert len(prompts) == 3
    assert 'old_family' not in prompts[0]
    assert 'old_family' not in prompts[1]
    assert 'DUPLICATE structural key rejected' in prompts[1]


def test_grounding_binds_primitive_to_selected_family():
    candidate = {"hypothesis_id": "discovered_primitive", "discovery_spec": {"operator": "difference", "left": "high", "right": "low", "threshold": 0, "direction": "above"}}
    selected = {"family": "smc_ict", "source_url": "https://example.test/source"}
    grounded = ground_candidate(candidate, selected)
    assert grounded["discovery_spec"]["mechanism_family"] == "smc_ict"


def test_family_profile_rejects_generic_smc_zscore():
    candidate = {
        "bc": 1, "parent_bc": 0, "hypothesis_id": "discovered_primitive",
        "conceptual_change": "x", "evidence_sources": ["x"], "rationale": "x",
        "is_testable": True, "oos_selection_used": False,
        "discovery_spec": {"mechanism_family": "smc_ict", "operator": "zscore", "left": "close", "window": 20, "threshold": 1, "direction": "above"},
    }
    ok, reason = validate_candidate(candidate, 1, 0)
    assert not ok
    assert reason == "family_operator_not_admissible"
