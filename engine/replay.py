"""Deterministic, research-only trade replay engine.

This is deliberately narrower than a live broker. It replays an already
materialized trade sequence against frozen marks and returns an auditable
portfolio/equity result. It never places orders and never decides promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ReplayTrade:
    timestamp: str
    side: str
    symbol: str
    price: float
    quantity: float
    trade_id: str = ""


def _finite_positive(value: Any, field: str) -> float:
    import math
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be finite and > 0")
    return number


def _normalize(trade: ReplayTrade | Mapping[str, Any]) -> ReplayTrade:
    if isinstance(trade, ReplayTrade):
        return trade
    return ReplayTrade(
        timestamp=str(trade.get("timestamp") or trade.get("executed_at") or ""),
        side=str(trade.get("side") or "").lower(),
        symbol=str(trade.get("symbol") or ""),
        price=_finite_positive(trade.get("price"), "price"),
        quantity=_finite_positive(trade.get("quantity"), "quantity"),
        trade_id=str(trade.get("trade_id") or trade.get("id") or ""),
    )


def replay(
    trades: Iterable[ReplayTrade | Mapping[str, Any]],
    *,
    starting_cash: float = 100_000.0,
    fee_rate: float = 0.0,
    max_position_pct: float = 100.0,
    max_drawdown_pct: float | None = None,
    marks: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Replay trades deterministically under a fixed challenge policy.

    Supported sides are buy/sell/short/cover. Shorting is explicit and may not
    silently cross a long position. Oversized sells/covers are rejected. The
    caller owns the governing policy; this function only enforces the supplied
    fixed values.
    """
    cash = _finite_positive(starting_cash, "starting_cash")
    fee_rate = float(fee_rate)
    max_position_pct = float(max_position_pct)
    if fee_rate < 0 or max_position_pct <= 0:
        raise ValueError("invalid replay policy")
    if max_drawdown_pct is not None and float(max_drawdown_pct) < 0:
        raise ValueError("max_drawdown_pct must be >= 0")

    normalized = [_normalize(t) for t in trades]
    ordered = sorted(normalized, key=lambda t: (t.timestamp, t.trade_id))
    positions: dict[str, dict[str, float]] = {}
    equity_curve = [cash]
    peak = cash
    max_drawdown = 0.0
    rejected: list[dict[str, Any]] = []

    def equity() -> float:
        total = cash
        for symbol, pos in positions.items():
            mark = float((marks or {}).get(symbol, pos["entry_price"]))
            if mark <= 0:
                raise ValueError(f"invalid mark for {symbol}")
            qty = pos["quantity"]
            if qty >= 0:
                total += qty * mark
            else:
                total += abs(qty) * (2 * pos["entry_price"] - mark)
        return total

    for trade in ordered:
        side = trade.side
        if side not in {"buy", "sell", "short", "cover"} or not trade.symbol:
            rejected.append({"trade_id": trade.trade_id, "reason": "invalid_trade"})
            break
        qty = trade.quantity
        price = trade.price
        fee = price * qty * fee_rate
        pos = positions.get(trade.symbol)
        current_qty = pos["quantity"] if pos else 0.0
        entry = pos["entry_price"] if pos else 0.0

        if side == "buy":
            if current_qty < 0:
                rejected.append({"trade_id": trade.trade_id, "reason": "buy_while_short"}); break
            cash -= price * qty + fee
            new_qty = current_qty + qty
            new_entry = ((current_qty * entry) + qty * price) / new_qty if current_qty else price
            positions[trade.symbol] = {"quantity": new_qty, "entry_price": new_entry}
        elif side == "sell":
            if current_qty <= 0 or qty > current_qty + 1e-12:
                rejected.append({"trade_id": trade.trade_id, "reason": "sell_exceeds_long"}); break
            cash += price * qty - fee
            new_qty = current_qty - qty
            if new_qty <= 1e-12:
                positions.pop(trade.symbol, None)
            else:
                positions[trade.symbol] = {"quantity": new_qty, "entry_price": entry}
        elif side == "short":
            if current_qty > 0:
                rejected.append({"trade_id": trade.trade_id, "reason": "short_while_long"}); break
            cash -= price * qty + fee
            new_qty = current_qty - qty
            short_qty = abs(current_qty)
            new_entry = ((short_qty * entry) + qty * price) / abs(new_qty) if current_qty < 0 else price
            positions[trade.symbol] = {"quantity": new_qty, "entry_price": new_entry}
        else:  # cover
            if current_qty >= 0 or qty > abs(current_qty) + 1e-12:
                rejected.append({"trade_id": trade.trade_id, "reason": "cover_exceeds_short"}); break
            cash += (2 * entry - price) * qty - fee
            new_qty = current_qty + qty
            if new_qty >= -1e-12:
                positions.pop(trade.symbol, None)
            else:
                positions[trade.symbol] = {"quantity": new_qty, "entry_price": entry}

        current_equity = equity()
        equity_curve.append(current_equity)
        peak = max(peak, current_equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - current_equity) / peak * 100.0)
        if current_equity > 0:
            largest = max((abs(p["quantity"]) * float((marks or {}).get(sym, p["entry_price"])) for sym, p in positions.items()), default=0.0)
            if largest / current_equity * 100.0 > max_position_pct + 1e-9:
                rejected.append({"trade_id": trade.trade_id, "reason": "max_position_pct_exceeded"}); break
        if max_drawdown_pct is not None and max_drawdown > max_drawdown_pct + 1e-9:
            rejected.append({"trade_id": trade.trade_id, "reason": "max_drawdown_exceeded"}); break

    ending_value = equity()
    return {
        "schema_version": 1,
        "trade_count": len(ordered),
        "accepted_trade_count": len(ordered) - len(rejected),
        "rejected": rejected,
        "starting_cash": starting_cash,
        "ending_value": ending_value,
        "return_pct": (ending_value - starting_cash) / starting_cash * 100.0,
        "max_drawdown_pct": max_drawdown,
        "equity_curve": equity_curve,
        "positions": positions,
        "policy": {
            "fee_rate": fee_rate,
            "max_position_pct": max_position_pct,
            "max_drawdown_pct": max_drawdown_pct,
        },
    }
