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


def generate_composites(*, max_components: int = 3) -> list[CompositeHypothesis]:
    """Generate bounded combinations; no OOS-dependent ranking or tuning."""
    import itertools

    names = sorted(HYPOTHESES)
    result: list[CompositeHypothesis] = []
    for size in range(2, max_components + 1):
        for combo in itertools.combinations(names, size):
            name = "combo__" + "__".join(combo)
            result.append(compose(name, list(combo)))
    return result
