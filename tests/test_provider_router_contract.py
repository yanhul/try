import math

import pytest

from research.provider_router import ground_candidate, normalize_structural_types
from research.btc_translation_policy import btc_translation_status, eligible_survivors


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


def test_non_executable_survivor_cannot_be_grounded():
    candidate = {"hypothesis_id": "discovered_primitive", "discovery_spec": {"operator": "identity", "left": "close", "threshold": 0, "direction": "above"}}
    selected = {"family": "china_a_share", "source_url": "https://example.test/source"}
    with pytest.raises(ValueError, match="non_executable_source_reached_grounding"):
        ground_candidate(candidate, selected)


def test_executable_survivor_family_is_canonicalized_deterministically():
    candidate = {"hypothesis_id": "discovered_primitive", "discovery_spec": {"operator": "identity", "left": "close", "threshold": 0, "direction": "above"}}
    selected = {"family": "smc_ict", "source_url": "https://example.test/source"}
    grounded = ground_candidate(candidate, selected)
    assert grounded["hypothesis_id"] == "mechanism_family"
    assert grounded["discovery_spec"] == {"mechanism_family": "smc_ict", "threshold": 0, "direction": "above"}


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


def test_filter_removes_incompatible_sources_before_selection():
    eligible, rejected = eligible_survivors([
        {"family": "smc_ict", "market": None, "title": "BTC/ETH ICT", "description": "crypto liquidity sweep MSS FVG", "source_url": "https://example.test/a"},
        {"family": "china_a_share", "market": "CN_A_SHARE", "title": "A-share", "description": "China stock portfolio", "source_url": "https://example.test/b"},
    ])
    assert [x["family"] for x in eligible] == ["smc_ict"]
    assert [x["family"] for x in rejected] == ["china_a_share"]
