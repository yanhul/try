# TRY autonomous repair — external authority provisioning contract

Status: **workflow wired to independent Git-backed issuer read API; live service/configuration NOT VERIFIED**.

The TRY repair workflow is intentionally unable to create or renew its own authority. Before enabling the privileged workflow, an independently governed issuer must provision the records below in the private Git-backed `yanhul/aios-authority-store` repository and deliver the read-only service URL/token through protected GitHub Actions secrets. The repository does not contain real credentials, and a green CI run does not prove provisioning has occurred.

## Required GitHub secret configuration

| Secret | Required value | Constraint |
|---|---|---|
| `AIOS_REPAIR_ISSUER_URL` | HTTPS base URL for the deployed authority-verifier Worker | Must be HTTPS; do not use a GitHub URL directly |
| `AIOS_REPAIR_ISSUER_READ_TOKEN` | Bearer token for `GET /v1/authority/runs/{run_id}` | Read-only issuer API token; no Git write permission |

| `AIOS_REPAIR_ATTESTATION_SECRET` | HMAC verification secret | Protected secret; available only to the isolated verifier step |
| `TRY_REPAIR_PROVIDER_URL` | HTTPS checkpoint provider URL | Must be HTTPS |
| `TRY_REPAIR_PROVIDER_TOKEN` | Repair proposal provider bearer token | Protected secret; exposed only around the proposal request |
| `TRY_REPAIR_CHECKPOINT_TOKEN` | Durable checkpoint API bearer token | Separate protected secret; exposed only during checkpoint HTTP calls, never to proposal code or candidate tests |
| Checkpoint configuration | Both `TRY_REPAIR_PROVIDER_URL` and `TRY_REPAIR_CHECKPOINT_TOKEN` are required for durable checkpoint read/write. | HTTPS endpoint plus protected bearer token |

The workflow must not put secret values into repository files, artifacts, logs, model prompts, test subprocesses, or the repair proposal. Configure secrets with least privilege and restrict which actors may run `workflow_dispatch`. The verifier Worker needs a separate fine-grained GitHub token with Contents: read only on the private `yanhul/aios-authority-store` repo (`GITHUB_READ_TOKEN`); the TRY issuer-read token is not that GitHub token.

## Issuer-side record requirements

Use the pinned AIOS authority implementation and its supported schemas/APIs; do not handcraft records merely to satisfy the TRY gate.

1. Persist a contract and permit through the independent issuer/governance process in the durable AIOS root.
2. Bind the contract to the exact GitHub Actions run ID: `task_id = try-ci-repair-<run_id>`.
3. Bind `actor = try-autonomous-repair`, `scope = repository`, capability `repo_patch@1`, allowed effect `external_effect`, and integer `max_attempts` from 1 through 3 (booleans are invalid).
4. Have the issuer create and persist the attestation using the AIOS authority mechanism and issuer-controlled HMAC secret. TRY must only load and verify it; TRY must never call `persist_attestation` or issue replacement authority.
5. Store contract, permit, and attestation in the private Git-backed authority repository under the immutable run/base-SHA prefix `records/<run_id>/<base_sha>/`;
   - `authority/contracts/<contract_id>.json`
   - `authority/permits/<permit_id>.json`
   - `authority/attestations/<permit_id>.json`
6. Make the records available read-only to the workflow and preserve the same durable state across runner invocations. A per-runner temporary directory is not durable authority storage.

## Preflight and rotation

The isolated `research/verify_repair_authority.py` step loads the exact issuer records through AIOS, calls `authorize()`, verifies the HMAC attestation, enforces run/actor/scope/capability/effect/budget constraints, and writes a receipt containing SHA-256 digests of the exact persisted bytes. The controller re-hashes those files and re-authorizes before proposal generation. Any missing record, changed bytes, invalid signature, identity mismatch, or missing secret must block before proposal/apply.

Because the contract task ID is bound to a specific workflow run ID, an issuer should provision authority for the exact target run rather than reuse a broad long-lived contract. Rotation/revocation must be performed by the issuer, not by TRY. Never copy an attestation or permit from another run and edit its identifiers.

## Evidence promotion contract

A test worker's `PASS`, `test:0:0` label, artifact filename, or checkpoint digest is not promoted evidence. Before a terminal PASS is accepted, TRY must resolve:
- a persisted AIOS effect in `OBSERVED_SUCCESS`, bound to the same contract, permit, actor, AIOS attempt ID, and provider observation;
- digest-verified effect evidence whose run identity is the AIOS attempt ID;
- each test evidence reference as a persisted `EV-*.json` record whose digest verifies, level is `VERIFIED_DIGITAL` or `PROMOTED`, run ID matches the GitHub workflow run, source/artifact lineage names the exact base SHA, and claim concerns testing/verification;
- any declared parent evidence reference, with valid digest and matching run/base lineage.

Evidence references must resolve within the persistent AIOS evidence directory; symlink/path escapes, duplicate refs, absent records, weak levels, wrong run IDs, and malformed SHA lineage block terminal promotion. The resolver verifies existing evidence; it does not mint evidence or promote worker assertions.

## Current acceptance status

The authority store is Git-backed; no R2 bucket is required. The COMMIT adapter source is implemented in the companion draft PR, but neither Worker is deployed or live-configured. CI does **not** prove authority issuance, Git API readback, GitHub App authorization, candidate creation, or adversarial E2E. Until those checks have real logs and readback receipts, authority provisioning and end-to-end evidence promotion remain **NOT VERIFIED**; TRY stays artifact-only.
