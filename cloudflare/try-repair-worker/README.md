# TRY → AIOS Repair Provider — Cloudflare Worker

This directory is the deployable Cloudflare runtime for the TRY-owned repair
reasoning bridge.

Boundary:

AIOS evidence → TRY reasoning → untrusted proposal → AIOS authority → mutation → tests → verification

The Worker never mutates an AIOS repository and never declares PASS.

## Endpoints

- GET /healthz
- POST /v1/repair/propose

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
