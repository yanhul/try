from engine.autonomous_evaluator import validation_gate


def metrics(**overrides):
    value = {
        "trade_count": 20,
        "profit_factor": 1.05,
        "total_return": 0.01,
        "max_drawdown": 0.20,
    }
    value.update(overrides)
    return value


def test_validation_gate_accepts_only_quality_validation():
    passed, reasons = validation_gate(metrics())
    assert passed is True
    assert reasons == []


def test_validation_gate_rejects_insufficient_sample():
    passed, reasons = validation_gate(metrics(trade_count=19))
    assert passed is False
    assert "INSUFFICIENT_VALIDATION_TRADES" in reasons


def test_validation_gate_rejects_weak_edge():
    passed, reasons = validation_gate(metrics(profit_factor=1.01))
    assert passed is False
    assert "PROFIT_FACTOR_BELOW_GATE" in reasons


def test_validation_gate_rejects_excessive_drawdown():
    passed, reasons = validation_gate(metrics(max_drawdown=0.31))
    assert passed is False
    assert "VALIDATION_DRAWDOWN_ABOVE_GATE" in reasons
