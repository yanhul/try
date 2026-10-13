# TRY cloud continuation contract

Status: implementation gate; the checkpoint API is bookkeeping, not authority.

## Event-driven loop

`CI failure event → observe immutable SHA/log tail → request proposal → AIOS gate → apply only under permit → run tests → persist evidence → resume or block`

The Worker only reasons and records a bounded checkpoint. It never commits patches, dispatches arbitrary shell commands, declares a verification PASS, or grants AIOS authority.

## Durable checkpoint API

- `POST /v1/repair/checkpoint` records the next checkpoint for a request.
- `GET /v1/repair/checkpoint/{request_id}` retrieves the durable record.
- Records are stored in a Cloudflare Durable Object, serialized per request.
- Identity is bound to request ID, repository and 40-character commit SHA.
- Attempts are bounded to 1–20 and must advance monotonically.
- A retry is accepted only after a BLOCKED record and an explicit RESUME phase.
- Phase transitions are validated; terminal DONE requires PERSIST plus a SHA-256 evidence digest.
- Identity conflict, invalid transition, stale attempt or missing terminal evidence fails closed.

The record does not prove the referenced evidence is authentic. AIOS must independently resolve and verify the evidence reference before any terminal decision. Never treat a Worker checkpoint as permission to mutate, a CI result, or a PASS receipt.

## Required deployment configuration

The Worker deployment needs a Durable Object binding named `REPAIR_CHECKPOINTS` and class migration `RepairCheckpoint`. The Gemini and bearer-token secrets remain Cloudflare secrets. Do not add credentials to repository files.

## Acceptance gates

1. Unit tests and Worker conformance tests pass.
2. Deploy workflow reports the Durable Object migration and binding are live.
3. Integration test persists a checkpoint, reads it after a separate request, rejects identity changes, invalid transitions and terminal completion without evidence digest.
4. AIOS bridge resolves the evidence digest to an actual persisted receipt; digest shape alone is not proof.
5. No merge/deploy claim until the cloud integration run is observed successful.
