# ASTRA ↔ Research PARA

## Contract

ASTRA and research are autonomous lanes over the same durable candidate/evidence frontier.

- Research owns experiment execution and scientific evidence.
- ASTRA owns bounded hypothesis mutation and generation lineage.
- AIOS-governed policy, evaluator, dataset, OOS lock, and promotion criteria are immutable.
- Lanes must not overwrite each other's durable state.
- A candidate may advance only from durable evidence; no self-attested promotion.

## Lifecycle

`research evidence → ASTRA mutation → research evaluation → terminal evidence → PROMOTE/REJECT → persist lineage → resume`

A research failure is input to the next ASTRA hypothesis, not campaign termination unless the fixed campaign terminal policy says so.

## Parallelism

The lanes may run concurrently, but writes are isolated by candidate/generation/effect identity and reconciled against the durable main state before persistence. The shared frontier is append/evidence based rather than last-writer-wins.

## Runtime promotion gate

ASTRA is considered integrated only after a real runtime run demonstrates:

1. mutation of an allowed field;
2. evaluation by the real research engine;
3. durable terminal evaluation evidence;
4. separate PROMOTE/REJECT decision;
5. parent/child lineage persistence;
6. restart/resume to the next generation.

Tests alone do not establish integration.
