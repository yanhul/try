# Algorithm worker provenance P1 — TRY integration

## Implemented in this branch

- The Cloudflare Worker has an Ed25519 receipt signer using a dedicated
  algorithm-receipt private key, key ID, worker ID, and immutable worker-build
  SHA-256 supplied by deployment configuration.
- The signed body binds the AIOS contract/permit, execution and attempt,
  worker identity/build, executor revision/source digest, spec/input digests,
  artifact/output digests, state and validity window.
- UNKNOWN is signed as IN_PROGRESS_OR_AMBIGUOUS and cannot carry artifact or
  output digests. The signer has no retry or promotion authority.
- TRY's AIOS boundary delegates verification to the AIOS-owned P1 verifier.
- The strict full-suite workflow checks out the AIOS P1 verifier commit for
  cross-repository conformance tests. This is a temporary stacked dependency;
  after AIOS PR #176 merges, update the pin to the AIOS merge commit.

## Not yet production-wired

The signer helper is not yet called by an algorithm-execution endpoint or
Durable Object lifecycle. P0's maze executor still runs as a Python library
function, not as this Cloudflare Worker. Therefore this branch does not claim
that a production algorithm worker is issuing these receipts, nor that the
worker build digest is already provisioned in production.

Before production use:
1. Add a bounded algorithm-execution endpoint/DO transition that persists
   DISPATCHED and execute_attempt before execution.
2. Persist immutable terminal result/artifact before issuing COMPLETED.
3. Return signed UNKNOWN after any ambiguous post-dispatch failure; never
   resubmit the same attempt automatically.
4. Configure the dedicated Ed25519 private key and matching AIOS public
   keyring out-of-band; rotate/revoke keys through deployment policy.
5. Bind the artifact digest to bytes AIOS independently retrieves and hashes.
6. Update the AIOS checkout pin to the merged AIOS verifier commit.

## Security semantics

A valid signature authenticates a statement by the holder of the pinned
private key. It does not provide hardware-backed workload attestation or prove
that a claimed executor binary was actually loaded. AIOS must still run the
independent algorithm verifier, and promotion remains a separate decision.
