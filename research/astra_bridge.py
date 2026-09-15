"""ASTRA <-> Research bridge primitives.

ASTRA may mutate research-candidate search parameters, but it never owns
research evaluation, OOS authority, terminal state, or promotion policy.
The bridge only creates deterministic child proposals and records their
lineage metadata; Research remains the evaluator of record.
"""
from __future__ import annotations
import copy
from dataclasses import dataclass
from typing import Any, Mapping
from engine.evolution_controller import Candidate, candidate_id, mutate
from research.autonomous_hypothesis import canonical_hash

@dataclass(frozen=True)
class AstraProposal:
    parent_research_hash: str
    astra_parent_id: str
    astra_candidate_id: str
    config: dict[str, Any]
    mutation: dict[str, Any]

def _discovery_mutations(spec: Mapping[str, Any]) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(spec.get("threshold"), (int, float)) and not isinstance(spec.get("threshold"), bool):
        value = float(spec["threshold"])
        for factor in (0.8, 1.25): out.append(("threshold", round(value * factor, 8)))
    if isinstance(spec.get("window"), int) and not isinstance(spec.get("window"), bool):
        windows = (3, 5, 10, 20, 50, 100)
        try: index = windows.index(spec["window"])
        except ValueError: index = -1
        if index >= 0:
            for next_index in (index - 1, index + 1):
                if 0 <= next_index < len(windows): out.append(("window", windows[next_index]))
    return out

def propose_from_research_candidate(parent: Mapping[str, Any], failure: Mapping[str, Any], *, used_ids: set[str] | None = None) -> AstraProposal:
    used = set(used_ids or set())
    spec = parent.get("discovery_spec")
    if not isinstance(spec, Mapping): raise ValueError("astra_bridge_requires_discovery_spec")
    if parent.get("candidate_hash") != canonical_hash(dict(parent)): raise ValueError("astra_bridge_parent_hash_mismatch")
    base = {"candidate_spec": copy.deepcopy(dict(spec))}
    astra_parent = Candidate(base)
    for field, value in _discovery_mutations(spec):
        mutated_spec = copy.deepcopy(dict(spec)); mutated_spec[field] = value
        child = Candidate(mutate(astra_parent.config, "candidate_spec", mutated_spec), astra_parent.id)
        if child.id in used: continue
        return AstraProposal(
            parent_research_hash=str(parent["candidate_hash"]),
            astra_parent_id=astra_parent.id,
            astra_candidate_id=child.id,
            config=dict(child.config),
            mutation={"field": field, "value": value, "failure_reason": failure.get("reason", "UNKNOWN")},
        )
    raise ValueError("astra_bridge_mutation_frontier_exhausted")

def materialize_research_candidate(parent: Mapping[str, Any], proposal: AstraProposal, *, bc: int) -> dict[str, Any]:
    spec = proposal.config.get("candidate_spec")
    if not isinstance(spec, Mapping): raise ValueError("astra_bridge_invalid_candidate_spec")
    child = copy.deepcopy(dict(parent)); child["bc"] = int(bc); child["parent_bc"] = int(bc) - 1
    child["discovery_spec"] = copy.deepcopy(dict(spec))
    child["conceptual_change"] = f"ASTRA bounded mutation: {proposal.mutation['field']}={proposal.mutation['value']}"
    child["evidence_sources"] = list(parent.get("evidence_sources") or []); child["evidence_sources"].append(f"astra:{proposal.astra_parent_id}->{proposal.astra_candidate_id}")
    child["candidate_hash"] = canonical_hash(child); return child

def proposal_record(proposal: AstraProposal, research_candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {"astra_parent_id": proposal.astra_parent_id,"astra_candidate_id": proposal.astra_candidate_id,"parent_research_candidate_hash": proposal.parent_research_hash,"research_candidate_hash": research_candidate["candidate_hash"],"mutation": copy.deepcopy(proposal.mutation),"status":"PROPOSED"}

__all__=["AstraProposal","materialize_research_candidate","proposal_record","propose_from_research_candidate"]
