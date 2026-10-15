# TRY cloud continuation contract

Status: implementation gate; the checkpoint API is bookkeeping, not authority.

## Event-driven loop

Target flow (not yet proven end-to-end):

`CI failure event → observe immutable SHA/log tail → request proposal → AIOS gate → apply only under permit → run tests → persist evidence → resume or block`

**Current integration boundary:** `.github/workflows/ci-event-receiver.yml` only validates and persists a notification envelope. It does not invoke `research/autonomous_repair.py`, the proposal relay, or the Cloudflare Worker. `.github/workflows/aios-repair-propose.yml` is manually dispatched. Therefore, the full event-to-repair chain is **NOT VERIFIED / BLOCKED**, even when unit and conformance CI are green.

`research/verify_repair_authority.py` runs as a separate trusted workflow step before the controller. It receives the HMAC secret, calls AIOS `authorize()`, loads contract/permit/attestation, verifies the persisted HMAC-SHA256 attestation, checks run-bound task ID, actor, repository scope, patch capability, allowed effect, and attempt budget, then writes a receipt bound to the exact contract/permit/attestation file digests. The verifier process exits before the controller starts, so the HMAC secret is not inherited by candidate-test subprocesses. The controller consumes the receipt, re-hashes the exact persisted records to detect replacement/tampering, and re-authorizes through AIOS before proposal generation. Neither process mints authority. Missing configuration, invalid signatures, stale/tampered receipts, or missing durable records fail closed before proposal/apply. Terminal PASS still requires the returned effect ID to resolve to a persisted AIOS `OBSERVED_SUCCESS` effect with matching contract/permit/actor, attempt/provider lineage, valid effect-evidence digest, and matching run ID. Every test evidence reference must resolve under the AIOS root's `evidence/` directory, pass `core.evidence.verify_evidence()`, use `VERIFIED_DIGITAL` or `PROMOTED`, match the run ID, include the base SHA in source/artifact lineage, and make a test/verification claim. Regression tests cover missing preflight receipts, receipt tampering, forged attestation, and evidence identity. This is code-level strictness only; it does not prove a real external issuer or deployed run is provisioned with those persisted records. It can retry only from a matching `BLOCKED` checkpoint that does not carry `reconciliation_required`. A `WORKING` checkpoint after process death is converted to an explicit `UNKNOWN` result and a reconciliation-required `BLOCKED` checkpoint. Subsequent invocations now remain `UNKNOWN`/blocked and cannot advance the attempt budget while that marker persists; they must not replay a potentially applied mutation. The proposal, working-tree mutation and AIOS receipt are not yet durably restored/reconciled, so this is safe-stop behavior, not complete crash recovery. The CI event receiver still persists notification only and does not dispatch repair; proposal remains manually dispatched. The Worker only reasons and records a bounded checkpoint. It never commits patches, dispatches arbitrary shell commands, declares a verification PASS, or grants AIOS authority.


## Privileged workflow and commit-authority boundary

The privileged `.github/workflows/try-autonomous-repair.yml` checks out the failed source only as a mutation workspace and executes the repair controller and isolated authority verifier from immutable TRY commit `9834ef6f506e15044c104512d038cd45cc7c56f0` (including the reconciliation-required retry lock, HMAC preflight, and receipt consumer) and AIOS authority code from immutable commit `cb38387f2dd0785136fcc6434a49e43233bad648`. Checkout and artifact-upload actions are also pinned to verified immutable SHAs; privileged dependencies do not follow mutable branch/tag refs. This prevents the failed revision from supplying the privileged repair controller. The workflow's GitHub permissions are read-only for repository contents and it must not execute a target-controlled publisher.

A successful test run is not enough to authorize Git commit or PR creation. The prior publisher path re-issued temporary AIOS authority and replayed the patch in a separate directory; that is not the same receipt as the mutation verified by the repair loop. That publisher path is disabled. Until a separately governed AIOS COMMIT adapter consumes a persisted commit decision/permit and the matching mutation + verification lineage, the workflow fails closed after exporting the candidate patch as an artifact. This is intentionally not an auto-PR claim.

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
