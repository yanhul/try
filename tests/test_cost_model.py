import pytest

from engine.metrics import Trade, calculate_metrics
from research.cost_model import CostModel


def test_cost_model_is_explicit_and_available():
    model = CostModel(fee_bps_per_side=10.0, slippage_bps_per_side=2.0)
    meta = model.metadata()
    assert meta["status"] == "AVAILABLE"
    assert meta["fee_bps_per_side"] == 10.0
    assert meta["slippage_bps_per_side"] == 2.0


def test_cost_model_reduces_profitable_trade():
    model = CostModel(fee_bps_per_side=10.0, slippage_bps_per_side=2.0)
    gross = (110.0 - 100.0) / 100.0
    result = calculate_metrics([Trade(100.0, 110.0, "bullish")], cost_model=model)
    assert result["total_return"] < gross
    assert result["cost_model"]["status"] == "AVAILABLE"


def test_cost_model_rejects_invalid_bps():
    with pytest.raises(ValueError):
        CostModel(fee_bps_per_side=-1)
    with pytest.raises(ValueError):
        CostModel(slippage_bps_per_side=10000)
