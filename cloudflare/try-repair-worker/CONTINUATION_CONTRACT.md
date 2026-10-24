# TRY cloud continuation contract

Status: checkpoint persistence/restart is live-verified; full repair authority and mutation recovery remain blocked. The checkpoint API is bookkeeping, not authority.

## Event-driven loop

Target flow (full chain not yet proven end-to-end):

`CI failure event → observe immutable SHA/log tail → request proposal → AIOS gate → apply only under permit → run tests → persist evidence → resume or block`

**Current integration boundary:** `.github/workflows/ci-event-receiver.yml` only validates and persists a notification envelope. It does not invoke `research/autonomous_repair.py`, the proposal relay, or the Cloudflare Worker. `.github/workflows/aios-repair-propose.yml` is manually dispatched. Therefore, the full event-to-repair chain is **NOT VERIFIED / BLOCKED**, even when unit and conformance CI are green.

`research/autonomous_repair.py` records checkpoint phases and fails closed when the Worker API is unavailable. It can retry only from a matching `BLOCKED` checkpoint; a `WORKING` checkpoint after process death is deliberately rejected because the proposal, working-tree mutation and AIOS receipt are not yet durably restored/reconciled. This is safe-stop behavior, not complete crash recovery. The Worker only reasons and records a bounded checkpoint. It never commits patches, dispatches arbitrary shell commands, declares a verification PASS, or grants AIOS authority.

## Durable checkpoint API

- `POST /v1/repair/checkpoint` records the next checkpoint for a request.
- `GET /v1/repair/checkpoint/{request_id}` retrieves the durable record.
- Records are stored in a Cloudflare Durable Object, serialized per request.
- Identity is bound to request ID, repository and 40-character commit SHA.
- Attempts are bounded to 1–20 and must advance monotonically.
- A retry is accepted only after a BLOCKED record and an explicit RESUME phase.
- Phase transitions are validated; terminal DONE requires PERSIST plus a SHA-256 evidence digest.
- Identity conflict, invalid transition, stale attempt or missing terminal evidence fails closed.

The current terminal digest binds the serialized `repair-result.json` artifact; it is not itself an AIOS receipt. The record does not prove the referenced evidence is authentic. A follow-up AIOS evidence resolver must bind this artifact digest to the actual persisted receipt and independently verify it before any terminal decision. Until that resolver is proven, `DONE` is checkpoint bookkeeping only—not PASS or authorization. Never treat a Worker checkpoint as permission to mutate, a CI result, or a PASS receipt.

## Required deployment configuration

The Worker deployment needs a Durable Object binding named `REPAIR_CHECKPOINTS` and class migration `RepairCheckpoint`. The Gemini and bearer-token secrets remain Cloudflare secrets. Do not add credentials to repository files.

## Observed live checkpoint validation

- Run: https://github.com/yanhul/try/actions/runs/38883554143
- Tested commit: `1418b944b79bb9e121199a51be6d7ec4ef6ef1f9`
- Result: `LIVE_DURABLE_CHECKPOINT_E2E` — PASS.
- The live Worker accepted OBSERVE, a separate Python process read it back after process restart, DECIDE advanced monotonically to version 2, and another fresh process read version 2 back.
- This proves live Durable Object checkpoint persistence/readback/restart only. It does **not** prove AIOS authority issuance, patch mutation, terminal evidence promotion, or crash recovery of a partially applied mutation.

## Acceptance gates

1. Unit tests and Worker conformance tests pass — PASS on the tested integration head.
2. Live Durable Object binding/persistence is operational — PASS by the live read/write/restart run above; this is functional evidence, not a deployment log.
3. Integration test persists a checkpoint and reads it after fresh processes — PASS. Identity conflicts, invalid transitions and terminal completion without evidence digest remain covered by conformance tests.
4. AIOS bridge resolves the evidence digest to an actual persisted receipt; digest shape alone is not proof — **BLOCKED / NOT VERIFIED**.
5. Full event-to-repair and authority → mutation → persisted effect → independent evidence → process-crash recovery — **BLOCKED / NOT VERIFIED**. Do not claim full cloud integration or autonomous repair success.
