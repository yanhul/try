"""Deterministic composition of registered research rules into strategy predicates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .hypotheses import HYPOTHESES


@dataclass(frozen=True)
class CompositeHypothesis:
    name: str
    components: tuple[str, ...]
    predicate: Callable[[dict, str], bool]


# Explicitly bounded search space: the research loop may compose these fixed
# context atoms, but it cannot expand the candidate universe autonomously.
COMPOSABLE_HYPOTHESES = (
    "sweep_confirmation",
    "sweep_wide_effort",
    "quiet_retest",
    "wyckoff_spring",
    "wyckoff_upthrust",
    "vsa_absorption",
    "vsa_expansion",
    "vpa_expansion",
    "vwap_alignment",
    "pnf_alignment",
    "gann_alignment",
    "mtf_alignment",
    "volume_profile_alignment",
)


def compose(name: str, components: list[str]) -> CompositeHypothesis:
    if not components:
        raise ValueError("composite hypothesis requires at least one component")
    unknown = [x for x in components if x not in HYPOTHESES]
    if unknown:
        raise KeyError(f"unknown hypothesis components: {unknown}")
    frozen = tuple(dict.fromkeys(components))

    def predicate(ctx: dict, direction: str) -> bool:
        return all(HYPOTHESES[c](ctx, direction) for c in frozen)

    return CompositeHypothesis(name=name, components=frozen, predicate=predicate)


def generate_composites(*, max_components: int = 3, max_results: int = 120) -> list[CompositeHypothesis]:
    """Generate a fixed, hard-capped composition space without OOS ranking."""
    import itertools

    if max_components < 2:
        return []
    if max_results <= 0:
        raise ValueError("max_results must be positive")

    result: list[CompositeHypothesis] = []
    names = COMPOSABLE_HYPOTHESES
    for size in range(2, max_components + 1):
        for combo in itertools.combinations(names, size):
            result.append(compose("combo__" + "__".join(combo), list(combo)))
            if len(result) >= max_results:
                return result
    return result
