# Strategy Replacement Policy

## Purpose
Prevent replacing or tuning `ReferenceStrategy` merely because one OOS slice looks weak or strong. Replacement is an evidence decision, not an optimization reaction.

## Current evidence
The current OOS robustness audit has 36 executed trades. Block bootstrap 95% intervals for total and compounded return both cross zero, and the MaxT multiple-testing adjusted p-value is not significant at 5%. Therefore the current evidence does **not** justify replacing the strategy.

## Decision gates
A replacement review is opened only when all of the following are true:

1. OOS sample reaches at least 60 executed trades.
2. Block-bootstrap 95% CI for total return excludes zero.
3. Block-bootstrap 95% CI for compounded return excludes zero.
4. MaxT multiple-testing adjusted p-value is below 0.05 for the pre-registered hypothesis family.
5. The candidate replacement is evaluated on data not used to design or select it.
6. The candidate must beat the incumbent under the same execution, cost, overlap, and walk-forward protocol; raw in-sample improvement is insufficient.

## What does NOT trigger replacement
- One bad walk-forward window.
- One favorable subgroup/bucket.
- A low win rate by itself.
- A small change in profit factor.
- Parameter tuning performed after seeing OOS results.
- A bootstrap interval that crosses zero.
- An unadjusted subgroup p-value.

## Escalation before replacement
If the gates are not met, keep the current strategy frozen and continue evidence collection. If a structural defect is discovered (look-ahead, leakage, execution-model error, incorrect event ordering, or a demonstrable implementation bug), fix the defect and restart the affected evaluation rather than treating the fix as a new strategy edge.

## Operational rule
`audit_strategy_decision_gate.py` is the machine-readable gate. Its decision must be recorded before any strategy modification. A `REVIEW_REPLACEMENT` result permits a controlled candidate comparison; it does not authorize immediate replacement.
