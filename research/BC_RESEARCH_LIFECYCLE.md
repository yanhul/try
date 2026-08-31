# BC Research Lifecycle

The controller is a strict autonomous research loop, not a strategy selector.

## States

`CANDIDATE -> TESTED -> IS_GATE -> VALIDATION_GATE -> FROZEN_OOS -> REPORT_ONLY -> TERMINAL`

A failed candidate enters `FAILURE_ANALYSIS_REQUIRED`. If and only if the failure-analysis artifact supplies an admissible, evidence-backed diagnostic cause, the research agent may generate exactly one next hypothesis. The controller validates it before queueing it.

## Hard rules

1. One conceptual change per BC.
2. Every generated hypothesis must cite one or more concrete evidence artifacts.
3. IS and validation are selection data; OOS is never selection data.
4. OOS parameters and the OOS criterion are frozen before OOS execution.
5. A BC may consume OOS at most once.
6. No grid search or winner selection on OOS.
7. Pytest must pass before a gate runs.
8. Missing/ambiguous decisions are blocking states, not implicit passes.
9. The agent may generate hypotheses, but only from failure-analysis evidence; it may not invent unsupported causes.
10. Generated candidates are schema-validated before entering the authoritative queue.
11. Each candidate receives an immutable SHA-256 candidate hash.
12. The OOS criterion cannot be changed after OOS evidence exists.
13. The controller has a bounded iteration budget. Exhaustion is terminal, not permission to continue indefinitely.
14. If the required failure-analysis evidence or research-agent capability is unavailable, the controller enters HOLD rather than fabricating a candidate.
15. The lifecycle state is persisted in `research/bc_lifecycle_state.json` so reruns resume safely.

## Autonomous transition

`REJECT -> FAILURE_ANALYSIS -> AGENT_HYPOTHESIS -> SCHEMA_GATE -> QUEUE -> IS -> VALIDATION -> REJECT/PROMOTE`

A rejected candidate therefore does not require a human `Go` between BCs, but it also cannot bypass the evidence and schema gates.

## Completion

The process is complete only when a frozen candidate has passed the required pre-OOS gates and its single OOS evaluation has been recorded as report-only, or when failure analysis produces no admissible testable cause, or when the configured iteration budget is exhausted.
