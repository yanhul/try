import pytest

from engine.cost_sensitivity import CostScenario, evaluate_cost_sensitivity
from engine.metrics import Trade


def test_cost_sensitivity_reduces_return():
    trades = [Trade(100, 110, "bullish"), Trade(100, 95, "bullish")]
    results = evaluate_cost_sensitivity(
        trades,
        (
            CostScenario("zero", 0.0),
            CostScenario("10bp", 0.001),
        ),
    )
    assert results[0]["metrics"]["total_return"] > results[1]["metrics"]["total_return"]


def test_cost_must_be_valid():
    with pytest.raises(ValueError):
        evaluate_cost_sensitivity(
            [Trade(100, 110, "bullish")],
            (CostScenario("bad", -0.01),),
        )
