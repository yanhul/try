# Repository governance absorption matrix

This document records **extracted control invariants**, not copied product features. A pattern is absorbed only when it can become a local invariant, test, or explicit boundary.

| Source pattern | Extracted invariant | Local absorption |
|---|---|---|
| OpenAgents / agent orchestration | Authority must be an explicit seam; stale evidence/capacity is not authority | `research/governance.py`: predecessor/evidence/authority/lineage checks; negative tests |
| Durable workflow / Conductor-style systems | Transport/scheduler state is not the source of truth; transitions are durable and idempotent | Campaign lifecycle transition contract + durable queue priority |
| Jixu-style action gating | Waiting/error/blocked state must not materialize or dispatch an action | Lifecycle `BLOCKED/HOLD/RETRY` precedence + permit denial |
| LobsterAI | Durable session, reconciliation on resume, bounded retry, provider boundary | Existing campaign reconciliation/provider lifecycle; retained as explicit controller contracts |
| Holmes / governed tool execution | Tool execution needs policy and evidence gates rather than caller convention | `authorize()` + `require_permit()` hard boundary |
| AutoResearch-style experiment loops | Candidate generation is separate from evaluation; failed evidence is not silently promoted | Candidate/OOS evidence checks and explicit OOS provenance |
| Trading research agents | Research execution must preserve experiment identity and evaluation lineage | Effect/receipt identities and idempotency key in governance primitives |

## Required chain

`EVENT -> STATE + PROVENANCE -> TRANSITION -> PERMIT -> EFFECT -> DISPATCH -> EXECUTE_ATTEMPT -> RECEIPT -> VERIFY -> PERSIST -> RESUME`

No lower stage may manufacture authorization for an earlier stage.

## Negative-path invariants

- `REPAIR_FAIL => controller step is skipped`.
- `BLOCKED/HOLD/UNKNOWN => no dispatch`.
- `EXECUTE => valid predecessor + evidence + authority + lineage + idempotency key`.
- `OOS_FAIL => explicit oos_failed_bc`.
- `MIGRATION => target == recorded oos_failed_bc`.
- `campaign_terminal == false => campaign_terminal_reason == null`.
- A receipt is bound to `effect_id + attempt_id + idempotency_key`.

## Absorption rule

Do not add a repo merely because it has an attractive feature. Extract the smallest enforceable invariant, map it to the control-plane boundary, add an adversarial test, and only then wire it into execution.
