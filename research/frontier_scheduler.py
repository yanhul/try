"""Adaptive research-frontier scheduling.

This module ranks *research opportunities*, never candidates for promotion.
It uses durable lifecycle outcomes only to allocate exploration budget across
mechanism families. Ties are deterministic so resume/replay is stable.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class FamilyStats:
    family: str
    trials: int
    successes: int
    failures: int
    priority: float


def _stable(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def _candidate_families(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    directory = root / "research" / "autonomous_candidates"
    if not directory.exists():
        return out
    for path in sorted(directory.glob("BC*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cid = str(data.get("candidate_hash") or data.get("candidate_id") or "")
            spec = data.get("discovery_spec") or {}
            family = str(spec.get("mechanism_family") or data.get("mechanism_family") or "")
            if cid and family:
                out[cid] = family
        except (OSError, ValueError, TypeError):
            continue
    return out


def _outcomes(root: Path) -> dict[str, tuple[int, int]]:
    """Return candidate -> (successes, failures) from authoritative lifecycle."""
    path = root / "research" / "research_lifecycle.jsonl"
    result: dict[str, tuple[int, int]] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            cid = str(event.get("candidate_id") or "")
            state = str(event.get("to_state") or "")
            if not cid:
                continue
            good, bad = result.get(cid, (0, 0))
            if state == "PROMOTED":
                good += 1
            elif state in {"REJECTED", "EXHAUSTED"}:
                bad += 1
            result[cid] = (good, bad)
        except (ValueError, TypeError):
            continue
    return result


def rank_families(families: Iterable[str], root: Path) -> list[FamilyStats]:
    """Rank exploration opportunities with UCB-style allocation.

    Untested families receive an infinite exploration priority. Tested families
    receive mean outcome plus an uncertainty bonus. This is scheduling only:
    no PROMOTE/REJECT decision is produced here.
    """
    families = sorted({str(f) for f in families if str(f)})
    mapping = _candidate_families(root)
    outcomes = _outcomes(root)
    stats: list[FamilyStats] = []
    for family in families:
        trials = successes = failures = 0
        for cid, fam in mapping.items():
            if fam != family:
                continue
            good, bad = outcomes.get(cid, (0, 0))
            successes += good
            failures += bad
            trials += good + bad
        if trials == 0:
            priority = float("inf")
        else:
            # Laplace smoothing prevents a single early success/failure from
            # dominating the frontier while preserving exploitation.
            mean = (successes + 1.0) / (trials + 2.0)
            total = max(1, sum(max(0, (outcomes.get(cid, (0, 0))[0] + outcomes.get(cid, (0, 0))[1])) for cid in mapping))
            import math
            bonus = math.sqrt(2.0 * math.log(total + 1.0) / trials)
            priority = mean + bonus
        stats.append(FamilyStats(family, trials, successes, failures, priority))
    return sorted(stats, key=lambda x: (-x.priority, _stable(x.family)))


def select_survivor(survivors: Iterable[Mapping[str, Any]], root: Path) -> tuple[Mapping[str, Any], FamilyStats]:
    """Select the highest-priority executable survivor deterministically."""
    items = [s for s in survivors if isinstance(s, Mapping)]
    if not items:
        raise ValueError("empty_survivor_frontier")
    families = [str(s.get("family") or "") for s in items]
    ranked = rank_families(families, root)
    by_family = {r.family: r for r in ranked}
    top = ranked[0]
    candidates = [s for s in items if str(s.get("family") or "") == top.family]
    candidates.sort(key=lambda s: _stable(str(s.get("candidate_id") or s.get("source_url") or "")))
    return candidates[0], by_family[top.family]


__all__ = ["FamilyStats", "rank_families", "select_survivor"]
