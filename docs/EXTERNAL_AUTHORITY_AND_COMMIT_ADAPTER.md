# External AIOS issuer and COMMIT adapter integration

Status: **client and protocol tests only; external services NOT DEPLOYED**.

This design intentionally separates three authorities:
- AIOS issuer: creates contracts, permits and HMAC attestations through the supported AIOS authority APIs. It is not part of the TRY repair controller.
- R2: durable private storage for issuer-produced records. R2 stores records; it does not grant authority.
- COMMIT adapter: independently verifies authority/evidence and uses a dedicated GitHub App installation to create a draft PR. It never merges.

The current branch adds `research/repair_external_integrations.py` as a fail-closed client. It does not create either service, configure secrets, deploy Workers, create a GitHub App, or prove live integration. Do not mark blockers closed based on unit tests.

## 1. Authority issuer API contract

The client expects:

`GET /v1/authority/runs/{run_id}`

Authenticated with a dedicated read-only bearer token. The issuer must authorize the caller and return records only for an exact repository, base SHA and workflow run. Expected JSON envelope:

```json
{
  "schema": 1,
  "run_id": "123456",
  "repository": "yanhul/try",
  "base_sha": "<40 lowercase hex SHA>",
  "contract_id": "<AIOS contract ID>",
  "permit_id": "<AIOS permit ID>",
  "records": {
    "contracts": {"content_b64": "<base64 exact bytes>", "sha256": "<sha256>"},
    "permits": {"content_b64": "<base64 exact bytes>", "sha256": "<sha256>"},
    "attestations": {"content_b64": "<base64 exact bytes>", "sha256": "<sha256>"}
  }
}
```

The issuer must generate records through the pinned AIOS `core.authority` and `core.attestation` APIs, after checking the issuer's independent approval policy. It must not accept arbitrary contract fields from TRY. At minimum it binds:
- `task_id = try-ci-repair-<run_id>`
- `actor = try-autonomous-repair`, `scope = repository`
- capability `repo_patch@1`, allowed effect `external_effect`
- attempt budget 1–3, exact repository and base SHA in issuer-side metadata
- issuer identity, permit identity, and issuer-controlled HMAC attestation.

Records are persisted to R2 only after the AIOS API has validated them. The signing/attestation secret is issuer-only; the workflow gets only the verification secret in the isolated verifier step. R2 must be private, with no public object access. The reader token must be read-only and scoped to the one object prefix. Do not use an R2 access key as the AIOS attestation secret.

Required workflow secrets after the issuer exists:
- `AIOS_REPAIR_ISSUER_URL`: HTTPS endpoint for the issuer read API.
- `AIOS_REPAIR_ISSUER_READ_TOKEN`: scoped read-only token.
- `AIOS_REPAIR_ATTESTATION_SECRET`: verifier-only HMAC verification secret.

The issuer should expose an operator-approved issuance operation separately from the read API. No unauthenticated, caller-selected contract/permit minting endpoint is acceptable. An issuer deployment is not accepted until positive and negative live tests verify exact run binding, wrong-repository denial, wrong-SHA denial, revoked/expired permit denial, record digest integrity and HMAC rejection.

## 3. COMMIT adapter API contract

The client expects:

`POST /v1/commit/candidate`

Authenticated with a token separate from the issuer token. Request includes the exact repository, base SHA, run ID, contract/permit IDs, patch bytes and digest, repair-result digest, authority-receipt digest, and deterministic idempotency key.

The adapter must independently:
1. Authenticate the caller and restrict repository to `yanhul/try`.
2. Fetch/verify the authority records and evidence from the independent AIOS issuer/store; never trust a caller-provided `verified: true` field by itself.
3. Verify permit capability, allowed effect, run/repository/base-SHA lineage, patch digest, evidence digests and revocation/expiry state.
4. Parse and apply the patch only against the exact expected base commit; reject path traversal, symlinks, binary or oversized changes outside policy, and base drift.
5. Use a dedicated GitHub App installed only on `yanhul/try`, with minimum repository permissions needed to create a branch and pull request. The App private key and installation ID are adapter-only secrets.
6. Make requests idempotent. If a timeout leaves creation uncertain, return `UNKNOWN`; reconcile the branch/PR via GitHub before any retry.
7. Create a **draft PR only**. Never merge or enable bypass of branch protections.

A confirmed response must include `status: CREATED`, exact repository/base SHA, exact patch digest, resulting 40-character head SHA, a GitHub PR URL under `/yanhul/try/pull/`, `draft: true`, and `merged: false`. Any other response remains blocked/unknown.

Required adapter secrets/configuration:
- `AIOS_COMMIT_ADAPTER_URL`: HTTPS endpoint.
- `AIOS_COMMIT_ADAPTER_TOKEN`: caller token for the adapter.
- Adapter-only: GitHub App ID, installation ID and private key, plus independent AIOS evidence/authority read access. These must never be passed to TRY's proposal or test subprocesses.

## 4. Acceptance gate

Do not call either blocker PASS until the following evidence exists:
- issuer deployment/version and private R2 policy verified;
- a real run-bound authority fetch with record digests, AIOS `authorize()`, HMAC verification and negative tampering tests;
- a real adapter request using the dedicated GitHub App, draft PR creation on the exact base SHA, and readback of the resulting head commit;
- retry/timeout reconciliation test proving no duplicate PR and no merge;
- full TRY workflow logs and artifacts tying authority receipt, patch digest, effect receipt and created PR together.

Until then, the client code can be tested in isolation, but blockers 1 and 3 remain **BLOCKED** and the repair workflow must remain artifact-only. Keep PR #49 draft; do not merge or deploy from this branch.
