import pytest

from research.family_registry import (
    DISCOVERY_FAMILIES,
    EXECUTABLE_FAMILIES,
    EVENT_FAMILIES,
    FAMILIES,
    direction_for_row,
    require_executable,
    REGISTRY_DIGEST, TAXONOMY_VERSION, taxonomy_for_family, validate_registry,
)


def test_every_discovery_family_is_canonical():
    assert len(DISCOVERY_FAMILIES) == 17
    assert DISCOVERY_FAMILIES <= FAMILIES.keys()


def test_executable_family_is_directional_and_evaluator_backed():
    assert EXECUTABLE_FAMILIES == {
        "momentum_trend", "mean_reversion", "smc_ict", "fvg_imbalance",
        "wyckoff_vsa_vpa", "vwap_volume_profile", "regime",
        "point_figure", "gann_reference",
    }
    assert all(FAMILIES[x].evaluator_enabled and FAMILIES[x].directional for x in EXECUTABLE_FAMILIES)


def test_unsupported_discovery_families_fail_closed():
    for family in {
        "volatility", "seasonality", "funding_basis_carry", "order_flow",
        "cross_sectional", "onchain", "options", "prediction_market",
        "execution_mev", "china_a_share",
    }:
        with pytest.raises(ValueError, match="unexecutable_family"):
            require_executable(family)


def test_event_family_mapping_is_canonical():
    assert EVENT_FAMILIES == {"smc_ict", "fvg_imbalance"}
    assert FAMILIES["smc_ict"].candidate_universe == "reference_event_ledger"
    assert FAMILIES["fvg_imbalance"].candidate_universe == "reference_event_ledger"


def test_direction_semantics_have_one_authority():
    assert direction_for_row({"momentum_trend": 1.0}, "momentum_trend") == "bullish"
    assert direction_for_row({"mean_reversion": -1.0}, "mean_reversion") == "bullish"
    assert direction_for_row({"mtf_fast_bullish": False}, "regime") == "bearish"
    assert direction_for_row({"point_figure": "X"}, "point_figure") == "bullish"
    assert direction_for_row({"gann_reference": -0.5}, "gann_reference") == "bearish"


def test_registry_is_layered_versioned_and_digest_stable():
    validate_registry()
    assert TAXONOMY_VERSION == "2.0.0"
    assert len(REGISTRY_DIGEST) == 64
    assert taxonomy_for_family("smc_ict")["layer"] == "family"
    assert taxonomy_for_family("smc_ict")["domain_id"] == "market_structure"
    assert taxonomy_for_family("point_figure")["layer"] == "primitive_reference"
    assert taxonomy_for_family("point_figure")["status"] == "EVALUATOR_ONLY"


def test_non_family_reference_primitives_are_not_discoverable():
    assert "point_figure" not in DISCOVERY_FAMILIES
    assert "gann_reference" not in DISCOVERY_FAMILIES
    assert FAMILIES["point_figure"].evaluator_kind == "reference_primitive"


def test_unknown_family_fails_closed():
    with pytest.raises(ValueError, match="unknown_family"):
        require_executable("invented_strategy_family")
