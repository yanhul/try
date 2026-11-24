# TRY → AIOS Repair Provider — Cloudflare Worker

This directory is the deployable Cloudflare runtime for the TRY-owned repair
reasoning bridge.

Boundary:

AIOS evidence → TRY reasoning → untrusted proposal → AIOS authority → mutation → tests → verification

The Worker never mutates an AIOS repository and never declares PASS.

## Endpoints

- GET /healthz
- POST /v1/repair/propose — idempotent by `request_id`; persists operation claim before calling Gemini
- GET /v1/repair/proposal/{request_id} — inspect the durable Gemini proposal operation/result
- POST /v1/repair/checkpoint — persist a validated, SHA-bound lifecycle checkpoint
- GET /v1/repair/checkpoint/{request_id} — resume by reading the durable checkpoint

## Secrets

Configure these in Cloudflare as Worker secrets:

- GEMINI_API_KEY — TRY-owned Gemini credential.
- TRY_PROVIDER_TOKEN — shared bearer token used only by the AIOS provider bridge.

Optional non-secret variable:

- GEMINI_MODEL (default: gemini-3.1-flash-lite)

Do not put either secret in wrangler vars or Git.

## Deploy

From this directory:

    uv run pywrangler deploy

Cloudflare's Python Worker runtime uses the `python_workers` compatibility flag.

## Durable continuation

The Worker binds a SQLite-backed Cloudflare Durable Object named `RepairCheckpoint`.
Checkpoints are immutable in identity (request ID + repository + commit SHA), versioned,
and transition-validated. Attempts are bounded (1–20); retries require a prior BLOCKED
record and an explicit RESUME phase. Terminal DONE requires PERSIST plus an evidence
SHA-256 digest. A digest's shape is not proof: AIOS must resolve it to a real receipt and
independently verify it before making any terminal decision.

This provides durable state across Worker invocations; it does not run an infinite process.
Progress continues on external events (CI completion, webhook, or explicit dispatch), with
AIOS retaining authority over patch application and verification.

## Gemini proposal operation ledger

`POST /v1/repair/propose` is now claimed in the same Durable Object namespace before the
Gemini request starts. The claim binds `request_id` to the exact request digest, repository,
commit SHA, and attempt. Reusing a request ID with different input is rejected.

- `COMPLETED`: the validated proposal is durably cached; replay returns the same proposal
  without another Gemini call.
- `FAILED`: an explicit provider rejection/protocol termination was recorded. This is not
  an automatic retry authorization.
- `UNKNOWN` / `IN_PROGRESS`: the provider call may have been accepted but no terminal result
  was durably recorded. Replay and lookup do not call Gemini again; `retry_allowed` is false.

A crash after Gemini responds but before the result is persisted remains `UNKNOWN` by design.
The endpoint is an operation-status source, not by itself an AIOS-authenticated provider
receipt or a retry permit. AIOS must independently bind and authorize any reconciliation.


### Trusted operation receipts

Configure Cloudflare secrets `TRY_OPERATION_RECEIPT_PRIVATE_KEY` (base64-encoded Ed25519 PKCS#8 DER private key) and `TRY_OPERATION_RECEIPT_KEY_ID`. The Worker signs operation receipts with the Cloudflare WebCrypto Ed25519 implementation; the private key never leaves TRY. AIOS pins only the matching 32-byte raw Ed25519 public key (base64) in `AIOS_TRY_OPERATION_KEYRING` under issuer `try.repair` with scope `try.operation.receipt.verify`. The bearer token alone is not receipt authority. Generate a fresh keypair in a trusted offline environment, place only the private-key encoding in the Worker secret store, and place only the public-key encoding in AIOS deployment configuration. Rotate by pinning the new public key before switching the Worker key ID/private key, then revoke the old key.

Only local configuration failures that occur before the Gemini request is sent are classified `FAILED / NOT_SUBMITTED`. Provider HTTP errors, malformed responses, timeouts, and crashes after submission remain `UNKNOWN`; they do not authorize retry. This is intentionally conservative because the Gemini chat-completions request has no independent operation lookup proving non-execution.