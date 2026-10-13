# TRY → AIOS Repair Provider — Cloudflare Worker

This directory is the deployable Cloudflare runtime for the TRY-owned repair
reasoning bridge.

Boundary:

AIOS evidence → TRY reasoning → untrusted proposal → AIOS authority → mutation → tests → verification

The Worker never mutates an AIOS repository and never declares PASS.

## Endpoints

- GET /healthz
- POST /v1/repair/propose
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
