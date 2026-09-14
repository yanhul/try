# `try` — LobsterAI-derived runtime patterns

This workload absorbs only runtime/session patterns that strengthen the AIOS boundary. `try` does not depend on LobsterAI.

## Absorbed contract

- The campaign is a **durable session**, not a one-shot process.
- Every resume loads `research/bc_lifecycle_state.json` and reconciles durable BC artifacts before selecting new work.
- The workflow scheduler/watchdog may trigger a non-terminal campaign, but it may not modify campaign policy or terminal criteria.
- Controller concurrency prevents duplicate campaign execution.
- Runtime/provider execution remains behind the AIOS adapter boundary.
- Provider output is accepted only after controller verification and durable persistence.
- Retry is bounded and stateful; no scheduler may turn an unresolved `UNKNOWN`/HOLD into success.
- Campaign terminality is explicit and persisted as `campaign_terminal` with `campaign_outcome`.

## Research-specific terminal contract

The campaign policy owns the terminal outcomes:

`EDGE_FOUND | NO_EDGE_FOUND | INCONCLUSIVE | BLOCKED`

A runtime/provider `SUCCESS` is **not** a research terminal result. A GitHub Actions job completing successfully is also not evidence of an edge.

## Required continuation chain

```text
scheduled wake
  -> load durable campaign state
  -> reconcile BC artifacts
  -> observe
  -> decide next bounded BC
  -> provider/runtime execution
  -> evaluator + gate
  -> OOS authority/execution when eligible
  -> persist state + lineage
  -> terminal OR durable resume
```

This is intentionally stricter than a generic scheduled-agent product: research policy, evidence, OOS lock and terminal criteria remain outside the provider/agent.
