from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradingCosts:
    """Explicit proportional round-trip costs for research evaluation.

    Fee is charged on both entry and exit. Slippage is expressed as a
    one-way proportional adverse fill assumption and therefore applies twice
    to a round trip. This model is deliberately simple; it must not be
    mistaken for exchange-specific execution simulation.
    """

    fee_rate: float = 0.0
    slippage_rate: float = 0.0

    def __post_init__(self) -> None:
        if self.fee_rate < 0 or self.slippage_rate < 0:
            raise ValueError("fee_rate and slippage_rate must be non-negative")
        if self.fee_rate >= 1 or self.slippage_rate >= 1:
            raise ValueError("fee_rate and slippage_rate must be below 1")

    @property
    def round_trip_cost(self) -> float:
        return 2.0 * (self.fee_rate + self.slippage_rate)
