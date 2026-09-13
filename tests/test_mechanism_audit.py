from research.discovery.mechanism_audit import audit


def test_trading_mechanism_registry_is_fail_closed():
    result = audit()
    assert result["fail_closed"] is True
    assert result["total_families"] == 18
    assert "smc_ict" in result["executable_families"]
    assert "fvg_imbalance" in result["executable_families"]
    assert "funding_basis_carry" in result["data_lane_required"]
    assert "order_flow" in result["data_lane_required"]
    assert "onchain" in result["data_lane_required"]
    assert "options" in result["data_lane_required"]
    assert "prediction_market" in result["data_lane_required"]
    assert "execution_mev" in result["data_lane_required"]
    assert "ml_rl" in result["research_only"]
