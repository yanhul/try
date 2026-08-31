from __future__ import annotations

from dataclasses import dataclass

from .metrics import Trade, calculate_metrics


@dataclass(frozen=True)
class CostScenario:
    name: str
    round_trip_cost: float


DEFAULT_SCENARIOS = (
    CostScenario("zero_cost", 0.0),
    CostScenario("10bp_round_trip", 0.001),
    CostScenario("20bp_round_trip", 0.002),
)


def evaluate_cost_sensitivity(
    trades: list[Trade],
    scenarios: tuple[CostScenario, ...] = DEFAULT_SCENARIOS,
) -> list[dict]:
    return [
        {
            "scenario": scenario.name,
            "round_trip_cost": scenario.round_trip_cost,
            "metrics": calculate_metrics(
                trades,
                round_trip_cost=scenario.round_trip_cost,
            ),
        }
        for scenario in scenarios
    ]
