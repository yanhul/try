# Durable Solution Lineage

This layer records research ancestry independently of the model context.

## Lifecycle

`OBSERVE -> LOAD LINEAGE -> HYPOTHESIZE -> IMPLEMENT -> RUN -> EVALUATE -> PERSIST -> PROMOTE/REJECT -> NEXT GENERATION`

## Rule

Agents may propose hypotheses, implementations and next experiments. They may not change the governing evaluator, acceptance criteria, validation/OOS boundary, evidence requirements, iteration budget, or terminal conditions.

## Minimum provenance

Every experiment should identify its parent artifacts/findings, code revision, configuration/data hashes, evaluator result, verdict, evidence, findings, constraints and unresolved claims.

Failures are retained as research assets. A later generation must be able to distinguish a failed mechanism from an untested mechanism and from an evaluator/protocol failure.
