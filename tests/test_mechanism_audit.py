from research.discovery.mechanism_audit import audit


def test_trading_mechanism_registry_is_fail_closed():
    result = audit()
    assert result["fail_closed"] is True
    assert result["authority"] == "research.family_registry"
    assert result["total_families"] == 19
    assert result["counts"] == {
        "EXECUTABLE": 7,
        "DISCOVERY_ONLY": 10,
        "EVALUATOR_ONLY": 2,
    }
    assert "smc_ict" in result["executable_families"]
    assert "fvg_imbalance" in result["executable_families"]
    assert "funding_basis_carry" in result["discovery_only"]
    assert "order_flow" in result["discovery_only"]
    assert "onchain" in result["discovery_only"]
    assert "options" in result["discovery_only"]
    assert "prediction_market" in result["discovery_only"]
    assert "execution_mev" in result["discovery_only"]
    assert "point_figure" in result["evaluator_only"]
    assert "gann_reference" in result["evaluator_only"]
    assert "ml_rl" not in result["executable_families"]
    assert "ml_rl" not in result["discovery_only"]
    assert "ml_rl" not in result["evaluator_only"]
