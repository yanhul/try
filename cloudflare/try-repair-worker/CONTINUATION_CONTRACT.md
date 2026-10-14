# TRY cloud continuation contract

Status: implementation gate; the checkpoint API is bookkeeping, not authority.

## Event-driven loop

Target flow (not yet proven end-to-end):

`CI failure event → observe immutable SHA/log tail → request proposal → AIOS gate → apply only under permit → run tests → persist evidence → resume or block`

**Current integration boundary:** `.github/workflows/ci-event-receiver.yml` only validates and persists a notification envelope. It does not invoke `research/autonomous_repair.py`, the proposal relay, or the Cloudflare Worker. `.github/workflows/aios-repair-propose.yml` is manually dispatched. Therefore, the full event-to-repair chain is **NOT VERIFIED / BLOCKED**, even when unit and conformance CI are green.

`research/autonomous_repair.py` records checkpoint phases and fails closed when the Worker API is unavailable. It must never mint its own capability, policy, contract, or permit. The runner requires externally issued `AIOS_REPAIR_CONTRACT_ID` and `AIOS_REPAIR_PERMIT_ID` plus a pre-provisioned persistent `AIOS_REPAIR_AUTHORITY_DIR`; absent configuration is recorded as BLOCKED before proposal/apply. Before asking the proposer for a patch, it calls AIOS `core.authority.authorize()` and `load_contract()` to resolve persisted records and verify contract/permit integrity, exact task ID for the CI run, actor, repository scope, patch capability, allowed effect, and attempt budget. Unit regression tests cover missing config, missing/temporary directories, resolver invocation, and resolver rejection. This proves the code path is wired, not that a real external issuer has provisioned records in a deployed run. It can retry only from a matching `BLOCKED` checkpoint; a `WORKING` checkpoint after process death is deliberately rejected because the proposal, working-tree mutation and AIOS receipt are not yet durably restored/reconciled. This is safe-stop behavior, not complete crash recovery. The Worker only reasons and records a bounded checkpoint. It never commits patches, dispatches arbitrary shell commands, declares a verification PASS, or grants AIOS authority.

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

## Acceptance gates

1. Unit tests and Worker conformance tests pass.
2. Deploy workflow reports the Durable Object migration and binding are live.
3. Integration test persists a checkpoint, reads it after a separate request, rejects identity changes, invalid transitions and terminal completion without evidence digest.
4. AIOS bridge resolves the evidence digest to an actual persisted receipt; digest shape alone is not proof.
5. No merge/deploy claim until the cloud integration run is observed successful.
