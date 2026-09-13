#!/usr/bin/env python3
"""Deterministic, explicit transaction-cost model for research promotion gates."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    """Per-side proportional fee and slippage assumptions, expressed in bps.

    These are research assumptions, not a claim about a particular venue/account.
    They are deliberately explicit and immutable for a run.
    """
    fee_bps_per_side: float = 10.0
    slippage_bps_per_side: float = 2.0
    label: str = "generic_spot_preregistered"

    def __post_init__(self) -> None:
        for name, value in (("fee_bps_per_side", self.fee_bps_per_side), ("slippage_bps_per_side", self.slippage_bps_per_side)):
            if not isinstance(value, (int, float)) or value < 0 or value >= 10000:
                raise ValueError(f"invalid_{name}")
        if not self.label:
            raise ValueError("invalid_cost_model_label")

    @property
    def round_trip_fee(self) -> float:
        return 2.0 * self.fee_bps_per_side / 10000.0

    @property
    def slippage_per_side(self) -> float:
        return self.slippage_bps_per_side / 10000.0

    def metadata(self) -> dict:
        return {
            "status": "AVAILABLE",
            "label": self.label,
            "fee_bps_per_side": self.fee_bps_per_side,
            "slippage_bps_per_side": self.slippage_bps_per_side,
            "fee_round_trip_fraction": self.round_trip_fee,
            "slippage_model": "adverse_price_per_side",
            "assumption_scope": "research_assumption_not_venue_specific",
        }

    def net_return(self, entry: float, exit: float, direction: str) -> float:
        if entry <= 0 or exit <= 0:
            raise ValueError("prices must be positive")
        slip = self.slippage_per_side
        fee = self.fee_bps_per_side / 10000.0
        if direction == "bullish":
            effective_entry = entry * (1.0 + slip)
            effective_exit = exit * (1.0 - slip)
        elif direction == "bearish":
            effective_entry = entry * (1.0 - slip)
            effective_exit = exit * (1.0 + slip)
        else:
            raise ValueError("invalid direction")
        gross_after_slippage = (effective_exit - effective_entry) / effective_entry if direction == "bullish" else (effective_entry - effective_exit) / effective_entry
        return gross_after_slippage - 2.0 * fee


DEFAULT_COST_MODEL = CostModel()
