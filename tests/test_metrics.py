import pytest

from engine.metrics import Trade, calculate_metrics, trade_return


def test_bullish_return():
    assert trade_return(Trade(100, 110, "bullish")) == pytest.approx(0.10)


def test_bearish_return():
    assert trade_return(Trade(100, 90, "bearish")) == pytest.approx(0.10)


def test_metrics():
    result = calculate_metrics([
        Trade(100, 110, "bullish"),
        Trade(100, 95, "bullish"),
        Trade(100, 120, "bullish"),
    ])

    assert result["trade_count"] == 3
    assert result["win_count"] == 2
    assert result["loss_count"] == 1
    assert result["win_rate"] == pytest.approx(2 / 3)
    assert result["profit_factor"] == pytest.approx(6.0)
    assert result["max_drawdown"] > 0


def test_empty_metrics():
    result = calculate_metrics([])

    assert result["trade_count"] == 0
    assert result["win_rate"] == 0.0
    assert result["profit_factor"] is None


def test_invalid_trade():
    with pytest.raises(ValueError):
        trade_return(Trade(0, 100, "bullish"))

    with pytest.raises(ValueError):
        trade_return(Trade(100, 110, "sideways"))
