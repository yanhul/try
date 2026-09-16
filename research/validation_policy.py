"""Single authoritative validation-quality policy for TRY research evaluators."""
from __future__ import annotations

EVALUATION_SPEC = {
    "stop_fraction": 0.01,
    "reward_multiple": 2.0,
    "cost_model_status": "AVAILABLE",
    "validation_basis": "NET_REQUIRED_FOR_PROMOTION",
    "min_validation_trades": 20,
    "min_validation_profit_factor": 1.05,
    "min_validation_total_return": 0.0,
    "max_validation_drawdown": 0.30,
}


def validation_gate(metrics):
    reasons = []
    trade_count = int(metrics.get("trade_count", 0) or 0)
    pf = metrics.get("profit_factor")
    total_return = metrics.get("total_return")
    drawdown = metrics.get("max_drawdown")
    if trade_count < EVALUATION_SPEC["min_validation_trades"]:
        reasons.append("INSUFFICIENT_VALIDATION_TRADES")
    if pf is None or pf < EVALUATION_SPEC["min_validation_profit_factor"]:
        reasons.append("PROFIT_FACTOR_BELOW_GATE")
    if total_return is None or total_return < EVALUATION_SPEC["min_validation_total_return"]:
        reasons.append("NON_POSITIVE_VALIDATION_RETURN")
    if drawdown is None or drawdown > EVALUATION_SPEC["max_validation_drawdown"]:
        reasons.append("VALIDATION_DRAWDOWN_ABOVE_GATE")
    return not reasons, reasons
