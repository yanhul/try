# H2 Controller Contract Boundary

The autonomous controller validates lifecycle artifacts before accepting them and before interpreting any gate result.

Required runtime boundaries:

1. A candidate must satisfy its identity, sequence, hash, evidence-source, testability, and OOS-selection contract before queue admission and evaluation.
2. Evaluation evidence must bind to the exact candidate and dataset identity and must explicitly prove that OOS was neither selected nor executed before gate interpretation.
3. BC state transitions must pass through the deterministic `transition()` contract; duplicate and out-of-sequence BCs are blocked.
4. Gate scripts remain the source of strategy-specific decision criteria. H2 does not tune or replace those thresholds.
5. Promotion remains a gate decision followed by the existing external AIOS authority check for OOS execution; the contract layer does not grant authority.
