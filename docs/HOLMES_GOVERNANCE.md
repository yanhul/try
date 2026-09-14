# Holmes-derived governance boundary

`try` may consume advisory findings from agents, analyzers, graph/impact tools, or model providers. These findings are never authoritative by themselves.

## Required chain

`ADVISORY FINDING -> BOUND EVIDENCE -> CONTROLLER GATE -> PROMOTION`

An advisory finding cannot directly create `EDGE_FOUND`, `NO_EDGE_FOUND`, `PASS`, or any other terminal/promotion state.

Evidence must bind to the same research execution context (`run_id`, provider, and claim). The controller remains the owner of promotion and terminal decisions.

This is a governance primitive, not a Holmes-Kit dependency. It complements the existing `AIOS_BOUNDARY.md` fail-closed rules and must not create a second authority plane.
