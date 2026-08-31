import pytest

from engine.costs import TradingCosts
from engine.metrics import Trade, calculate_metrics, trade_return


def test_round_trip_cost_is_two_way_fee_plus_slippage():
    costs = TradingCosts(fee_rate=0.001, slippage_rate=0.0005)
    assert costs.round_trip_cost == pytest.approx(0.003)


def test_costs_reduce_trade_return():
    costs = TradingCosts(fee_rate=0.001, slippage_rate=0.0005)
    assert trade_return(Trade(100, 110, "bullish"), costs.round_trip_cost) == pytest.approx(0.097)


def test_negative_cost_rejected():
    with pytest.raises(ValueError):
        TradingCosts(fee_rate=-0.001)
