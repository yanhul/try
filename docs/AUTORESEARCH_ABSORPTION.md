# Autoresearch Absorption

TRY adopts the useful research-harness pattern from Karpathy's autoresearch without copying its model-training implementation.

## Research loop

`HYPOTHESIS -> PROPOSE -> RUN -> MEASURE -> COMPARE -> KEEP/REJECT -> PERSIST -> RESUME`

This loop must execute under the existing TRY protocol:

`IS -> VALIDATION -> OOS LOCKED -> WALK-FORWARD`

A metric improvement in IS alone is never sufficient for promotion.

## Immutable boundary

The agent may mutate strategy/experiment code and explicitly permitted parameters only. These remain immutable during a campaign unless the campaign itself is restarted under a new policy/data identity:

- raw dataset and data-integrity rules
- event definitions and causal semantics
- reference evaluator
- transaction/cost assumptions
- IS/validation/OOS partitioning
- OOS lock
- promotion/rejection criteria
- evidence and lineage requirements

## Experiment record

Each experiment should be identifiable by:

- experiment_id
- hypothesis_id
- parent experiment
- code revision
- dataset identity
- configuration identity
- budget
- measurement/evaluation result
- failure classification when applicable
- final decision
- evidence/receipt references

## Failure semantics

`FAILED`, `CRASHED`, `INVALID`, and `REJECTED` are distinct. A recoverable execution failure can enter a bounded repair/retry path. A failure must not be silently converted into a successful experiment or removed from the campaign ledger.

## Baseline comparison

Candidate changes are compared against a fixed baseline under the same evaluation contract. Promotion is a gated decision, not a direct consequence of a higher single metric.

## Research organization

The campaign may separate roles such as explorer, experimenter, critic, validator, and promoter. These roles do not gain authority to modify the governing research policy.

## Relationship to AIOS

TRY owns trading-research semantics. AIOS owns authority, durable execution, evidence, lineage, and resume behavior. The Karpathy patterns are absorbed as research-loop primitives inside that boundary.
