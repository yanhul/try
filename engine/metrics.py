from dataclasses import dataclass

from research.cost_model import CostModel


@dataclass(frozen=True)
class Trade:
    entry: float
    exit: float
    direction: str
    entry_bar: int | None = None
    exit_bar: int | None = None
    exit_reason: str | None = None


def trade_return(t: Trade, round_trip_cost: float = 0.0, *, cost_model: CostModel | None = None) -> float:
    if t.entry <= 0:
        raise ValueError("entry must be positive")
    if round_trip_cost < 0 or round_trip_cost >= 1:
        raise ValueError("round_trip_cost must be in [0, 1)")
    if cost_model is not None:
        if round_trip_cost != 0.0:
            raise ValueError("use either round_trip_cost or cost_model, not both")
        return cost_model.net_return(t.entry, t.exit, t.direction)
    if t.direction == "bullish":
        gross = (t.exit - t.entry) / t.entry
    elif t.direction == "bearish":
        gross = (t.entry - t.exit) / t.entry
    else:
        raise ValueError("invalid direction")
    return gross - round_trip_cost


def calculate_metrics(trades: list[Trade], round_trip_cost: float = 0.0, *, cost_model: CostModel | None = None) -> dict:
    returns = [trade_return(t, round_trip_cost, cost_model=cost_model) for t in trades]
    if not returns:
        result = {"trade_count": 0, "win_count": 0, "loss_count": 0, "win_rate": 0.0, "total_return": 0.0, "avg_return": 0.0, "profit_factor": None, "max_drawdown": 0.0}
        if cost_model is not None:
            result["cost_model"] = cost_model.metadata()
        return result
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    equity = 1.0
    peak = equity
    max_drawdown = 0.0
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak
        max_drawdown = max(max_drawdown, drawdown)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    result = {"trade_count": len(returns), "win_count": len(wins), "loss_count": len(losses), "win_rate": len(wins) / len(returns), "total_return": equity - 1.0, "avg_return": sum(returns) / len(returns), "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None, "max_drawdown": max_drawdown}
    if cost_model is not None:
        result["cost_model"] = cost_model.metadata()
    return result
