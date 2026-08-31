# BC Research Lifecycle

The controller is a resumable gate runner, not a strategy selector.

## States

`CANDIDATE -> TESTED -> IS_GATE -> VALIDATION_GATE -> FROZEN_OOS -> REPORT_ONLY -> TERMINAL`

A failed candidate enters `FAILURE_ANALYSIS_REQUIRED`; a new candidate may only be introduced when its hypothesis has a documented, repeatable diagnostic cause.

## Hard rules

1. One conceptual change per BC.
2. IS and validation are selection data; OOS is never selection data.
3. OOS parameters are frozen before OOS execution.
4. A BC may consume OOS at most once.
5. No grid search or winner selection on OOS.
6. Pytest must pass before a gate runs.
7. Missing/ambiguous decisions are blocking states, not implicit passes.
8. A rejected candidate does not automatically become a new strategy.
9. Failure analysis may justify a future hypothesis only when the diagnostic separation is fixed and directionally repeatable across IS and validation.
10. The lifecycle state is persisted in `research/bc_lifecycle_state.json` so reruns resume safely.

## Completion

The process is complete only when a frozen candidate has passed the required pre-OOS gates and its single OOS evaluation has been recorded as report-only, or when failure analysis produces no admissible testable cause.
