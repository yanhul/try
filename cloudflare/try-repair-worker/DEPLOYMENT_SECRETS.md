# Deployment secrets and staged activation

This Worker is named `try-aios-repair-provider`. Its checked-in `wrangler.jsonc`
does not define a named `production` environment, so use the default environment
and do not pass `--env production` unless a named environment is added deliberately.

## Required Worker secrets

The Wrangler configuration declares all four as required. Upload/deploy must fail
if any are absent:

- `GEMINI_API_KEY` — existing TRY-owned Gemini credential.
- `TRY_PROVIDER_TOKEN` — existing AIOS-to-TRY bearer transport credential.
- `TRY_OPERATION_RECEIPT_PRIVATE_KEY` — base64 PKCS#8 DER Ed25519 private key.
- `TRY_OPERATION_RECEIPT_KEY_ID` — opaque key ID; must equal the AIOS-pinned ID.

The last two values must come from the locally generated keypair. Never commit them,
paste them into GitHub issues/PRs, or place them in Wrangler `vars`.

## Stage the receipt secrets without deploying

From `cloudflare/try-repair-worker`, after authenticating Wrangler to the intended
Cloudflare account, use the local staging helper:

```powershell
.\stage-receipt-secrets.ps1 -Stage
```

It reads the private key and matching key ID from
`%USERPROFILE%\\.aios-secure-keys`, validates their encodings, writes a short-lived
temporary JSON file restricted to the current Windows identity, invokes
`wrangler versions secret bulk`, and deletes the temporary file in a `finally`
block. Secret values are not placed in process arguments or printed by the script.
The helper requires an authenticated Wrangler session and the locally installed
Wrangler version to support `versions secret bulk`.

The command stages a Worker version; it does not activate it. Record the returned
version ID privately. Do not run `wrangler versions deploy` until all four required
secrets have been confirmed present and the staged version has been reviewed.

If your installed Wrangler does not support `versions secret put`, stop and inspect
`npx wrangler versions secret put --help`; do not fall back to `wrangler secret put`
because that command deploys immediately.

## AIOS and Gateway configuration boundaries

AIOS deployment must receive:

- `AIOS_TRY_OPERATION_KEYRING`: JSON public-key keyring for issuer `try.repair`.
- `AIOS_GATEWAY_RETRY_PRIVATE_KEY_FILE`: path to the AIOS-only PEM private key.

Gateway deployment must receive:

- `AIOS_GATEWAY_RETRY_PUBLIC_KEYS`: JSON map containing only the matching Gateway
  retry-permit public key in raw-key hex encoding.

Never copy the AIOS Gateway private key into Gateway. Never copy the TRY receipt
private key into AIOS or Gateway. Keep the two Ed25519 keypairs independent.

## Activation gate

Do not activate a staged Worker version until:

1. All four required Worker secrets are present in the intended Cloudflare account.
2. The TRY key ID matches the public key pinned in AIOS.
3. The Gateway public-key map matches the AIOS RetryPermit signer key ID.
4. AIOS can load its keyring and signer in the actual runtime.
5. Gateway can load its public-key map in the actual runtime.
6. An end-to-end test proves receipt verification, durable reconciliation, permit
   signing, Gateway permit verification, single-use nonce/fence behavior, and
   crash/replay handling.

A local cryptographic test is not an end-to-end deployment test. An `UNKNOWN`
operation remains non-retryable unless independent reconciliation proves
`PROVEN_NOT_SUBMITTED`. Do not relax this condition to make deployment tests pass.
