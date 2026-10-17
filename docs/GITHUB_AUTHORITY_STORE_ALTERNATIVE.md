# No-card authority issuer/store alternative

Status: **design only — not provisioned, not wired, not verified**.

This is the no-Cloudflare-billing alternative for PR #49. It uses GitHub Actions plus a separate private Git repository as a versioned authority-record store. It is not equivalent to an independently administered object-lock/WORM store: GitHub repository owners can still change repository settings or history. The security boundary must therefore come from separate repository access, protected issuer workflow, AIOS validation, signed/HMAC-attested records, and fail-closed readback.

## Decision

Use two separate repositories:

- `yanhul/try`: consumes authority read-only; never issues authority and never writes to the store.
- `yanhul/aios-authority-store` (proposed name; must be created explicitly): private repository holding only run-scoped authority records and an issuer workflow. This is a design name, not a claim that the repository exists.

Do not store authority in the TRY repository itself: the actor who can change the repair controller must not also be able to mint the authority it consumes.

## Issuer workflow

Create a manually dispatched workflow in the store repository, gated by a protected GitHub Environment named `authority-issuance` with required reviewer approval if the account's repository settings support it. The workflow must:

1. Accept only `run_id`, `repository`, `base_sha`, and a bounded attempt budget as inputs. Reject repositories other than `yanhul/try`, non-40-hex SHA values, non-decimal run IDs, and budgets outside 1–3.
2. Fetch the named TRY workflow run using a narrowly scoped, read-only GitHub credential; independently verify run ID, repository, failed source workflow, branch, and exact head SHA. Never trust caller-supplied identity fields alone.
3. Check out `yanhul/AIOS` at an explicitly reviewed immutable commit SHA and validate the current capability registry and policy. Do not follow `main` at issuance time.
4. Use the pinned AIOS `core.authority` APIs (`persist_contract`, `persist_permit`, `persist_attestation`) to create the records. Do not handcraft JSON. Bind `task_id=try-ci-repair-<run_id>`, actor `try-autonomous-repair`, scope `repository`, capability `repo_patch@1`, effect `external_effect`, the exact repo/SHA in issuer-controlled metadata, and attempt budget 1–3.
5. Validate the persisted records by reloading them and calling AIOS `authorize()` and `verify_attestation()`. Compute SHA-256 digests over the exact bytes.
6. Write only the run-scoped files to the store repository using a write credential available only to the issuer workflow. Use a deterministic path such as `records/yanhul/try/<run_id>/<base_sha>/`. Fail if the path already exists with different bytes; never silently overwrite or reissue a conflicting permit.
7. Read the committed files back from the resulting commit, verify their bytes and digests, and emit a receipt containing issuer workflow run, store commit SHA, AIOS commit SHA, target run/repo/base SHA, IDs, and digests. Do not expose the HMAC secret in artifacts or logs.

The issuer's write credential and `AIOS_REPAIR_ATTESTATION_SECRET` must exist only as protected secrets in the store repository/environment. The secret used to verify the HMAC in TRY must be a separate read/verify-only secret; TRY must not receive issuer write credentials.

## Read path from TRY

The current `research/repair_external_integrations.py` expects an HTTPS issuer API at `GET /v1/authority/runs/{run_id}`. A private Git repository does not itself provide that API, so do **not** set `AIOS_REPAIR_ISSUER_URL` to a GitHub web URL and assume it implements the contract.

For a no-card first iteration, use a pinned GitHub API read client in a separate integration module/workflow step:

- Fetch the exact record files from the private store repository at the immutable store commit SHA referenced by the issuance receipt.
- Authenticate with a dedicated fine-grained read-only credential scoped to the store repository's Contents: read permission. Keep it out of proposal generation, candidate tests, and artifacts.
- Verify the receipt's target run/repository/base SHA, store commit SHA, exact expected path set, content digests, AIOS contract/permit identity, and HMAC attestation before calling the existing isolated authority preflight.
- Materialize only the three expected files under a fresh runner-temporary directory, reject symlinks/path escapes, and never accept a record from a branch name that can move after issuance.
- Because `verify_repair_authority.py` currently rejects temporary authority roots, implement an explicit reviewed mode that verifies a content-addressed snapshot and receipt without weakening its current production check. Until that code exists and has tests, the current preflight cannot simply be pointed at a GitHub checkout.

If an HTTPS API contract is mandatory, deploy a separate thin read-only service later. The store design alone does not provide that endpoint.

## Credentials and permissions

Required setup is manual and is not performed by this PR:

- Create the separate private store repository.
- Configure issuer Environment approval / branch rules and restrict who can modify its workflow and protected secrets.
- Add issuer-only write credential and issuer HMAC secret to the store repository's protected environment.
- Add a separate fine-grained read-only store credential to `yanhul/try` as a GitHub Actions secret.
- Restrict issuer read access to the relevant TRY workflow-run metadata.
- Pin all third-party Actions by full commit SHA. Use least-privilege workflow permissions; no `contents: write` in the TRY repair job.
- Do not put credentials or authority JSON in this repository, PR diff, issue comments, logs, or model prompts.

GitHub Actions artifacts are not the durable authority store: their retention is bounded and configurable. They may carry test evidence/receipts, but the authority records must be read back from the private store commit. See the official documentation on [artifact retention](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository) and [OIDC/workflow identity](https://docs.github.com/en/actions/reference/security/oidc). OIDC is useful when a supported external service trusts GitHub-issued tokens; it does not by itself create a database, private store, or issuer API.

## Security limitations

- This is versioned storage, not immutable/WORM storage. A repository administrator could alter settings, delete records, or rewrite history. Preserve the immutable store commit SHA and receipt; verify signed records and digests on every read. For stronger administrative separation, a second owner/org or external immutable storage is preferable.
- A PAT-based read path introduces a credential that must be rotated and scoped. If the GitHub account/settings do not allow required protections, stop rather than pretend they are enabled.
- A manually approved issuance is a deliberate first version; it is not autonomous self-issuance. Automated issuance requires a separate trusted policy decision and audit trail.
- The COMMIT adapter and its dedicated GitHub App remain separate and unimplemented. Do not grant the issuer's store-write credential to the COMMIT adapter or TRY.
- No code path may turn a failed read, timeout, stale store SHA, invalid signature, mismatch, or conflicting record into PASS. Treat an ambiguous write as UNKNOWN and reconcile by querying the exact target path/commit before retrying.

## Acceptance gate

Do not mark the alternative provisioned until there is evidence for all of the following:

1. The private store repository exists, is private, and its settings/access controls were checked.
2. A real approved issuer run uses the pinned AIOS APIs and commits the three records.
3. The issuer reads back the exact committed bytes and validates AIOS authorization, HMAC, and digests.
4. TRY fetches by immutable store commit SHA and verifies run/repository/base-SHA binding.
5. Negative live tests reject wrong run, wrong repository, wrong SHA, tampered bytes, invalid HMAC, missing/revoked permit, and timeout/UNKNOWN.
6. A full repair E2E proves authority → candidate mutation → persisted effect → independently verified evidence → crash/recovery. This remains separate from the store smoke test.
7. PR #49 remains draft; no merge, deployment, or COMMIT enablement as part of this design change.

Current result: **NOT PROVISIONED / NOT VERIFIED**. This document is a proposed path, not proof of service deployment.
