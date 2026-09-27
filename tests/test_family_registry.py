import pytest

from research.family_registry import (
    DISCOVERY_FAMILIES,
    EXECUTABLE_FAMILIES,
    EVALUATOR_FAMILIES,
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
    }
    assert {"point_figure", "gann_reference"} <= EVALUATOR_FAMILIES
    assert all(FAMILIES[x].status == "EXECUTABLE" and FAMILIES[x].evaluator_enabled for x in EXECUTABLE_FAMILIES)


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


def test_executable_families_have_evaluator_dispatch_closure():
    from engine.autonomous_evaluator import mechanism_predicate

    for family in EXECUTABLE_FAMILIES:
        predicate = mechanism_predicate({"mechanism_family": family})
        assert callable(predicate)


def test_evaluator_only_primitives_are_not_executable():
    for family in ("point_figure", "gann_reference"):
        with pytest.raises(ValueError, match="unexecutable_family"):
            require_executable(family)


def test_executable_data_lane_is_closed():
    for family in EXECUTABLE_FAMILIES:
        spec = FAMILIES[family]
        assert spec.data_requirement
        assert spec.data_adapter
        assert spec.evaluator_kind


def test_registry_contains_no_legacy_ml_rl_or_duplicate_execution_authority():
    assert "ml_rl" not in FAMILIES
    assert all(
        spec.status in {"EXECUTABLE", "DISCOVERY_ONLY", "EVALUATOR_ONLY"}
        for spec in FAMILIES.values()
    )


def test_unknown_family_fails_closed():
    with pytest.raises(ValueError, match="unknown_family"):
        require_executable("invented_strategy_family")
