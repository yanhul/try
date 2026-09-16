# Repository governance absorption matrix

This document records extracted control invariants, not copied product features. A pattern is absorbed only when it becomes a local invariant, test, or explicit boundary.

| Source pattern | Extracted invariant | Local absorption |
|---|---|---|
| OpenAgents / orchestration | Authority is an explicit seam; stale evidence/capacity is not authority | `research/governance.py` provenance gates |
| Durable workflow systems | Transport/scheduler state is not source of truth; transitions are durable/idempotent | Campaign transition contract + durable queue |
| Jixu-style action gating | Waiting/error/blocked state must not materialize or dispatch an action | Lifecycle precedence + permit denial |
| LobsterAI | Durable session, reconciliation, bounded retry, provider boundary | Existing campaign controller contracts |
| Governed tool execution | Execution needs policy and evidence gates | `authorize()` + `require_permit()` |
| AutoResearch loops | Candidate generation is separate from evaluation | Candidate/OOS evidence gates |
| Trading research agents | Preserve experiment identity and evaluation lineage | Effect/receipt identities + idempotency |

## Required chain

`EVENT -> STATE + PROVENANCE -> TRANSITION -> PERMIT -> EFFECT -> DISPATCH -> EXECUTE_ATTEMPT -> RECEIPT -> VERIFY -> PERSIST -> RESUME`

No lower stage may manufacture authorization for an earlier stage.

## Negative-path invariants

- `REPAIR_FAIL => controller step is skipped`.
- `BLOCKED/HOLD/UNKNOWN => no dispatch`.
- `EXECUTE => predecessor + evidence + authority + lineage + idempotency key`.
- `OOS_FAIL => explicit oos_failed_bc`.
- `MIGRATION => target == recorded oos_failed_bc`.
- `campaign_terminal == false => campaign_terminal_reason == null`.
- Receipt identity binds `effect_id + attempt_id + idempotency_key`.
