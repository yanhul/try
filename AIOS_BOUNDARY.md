# AIOS Boundary Contract — `try`

This repository is an execution/research substrate, not the governing control plane.

## Authority invariants

- **Policy owner:** `research/bc_controller.py` and repository workflow policy.
- **Agent authority:** bounded hypothesis generation/execution only.
- **Terminal/promotion authority:** controller + registered gate/OOS path; the agent cannot redefine them.
- **Durability:** controller state and lineage are persisted before/after bounded work and the loop can resume.
- **Verification:** evaluator + BC gate precede promotion; OOS is frozen and executed once per candidate hash.
- **Fail closed:** missing baseline, failure analysis, gate, evaluator, explicit decision, or OOS protocol causes HOLD rather than fabricated PASS.

## AIOS adoption status

| Boundary | Status |
|---|---|
| Observe → Decide → Act → Verify → Persist → Resume | IMPLEMENTED |
| Policy outside agent | IMPLEMENTED |
| Immutable candidate/OOS evidence boundary | IMPLEMENTED |
| Explicit generalized permit/capability object | AIOS-BACKED |
| General contract/permit/attestation verifier | AIOS-BACKED — `engine/aios_boundary.py` delegates to `AIOS.core.contract` + `AIOS.core.attestation` |
| External-effect receipt/reconciliation layer | AIOS-BACKED at the central runner; TRY domain effects remain governed by TRY controller |
| Evolution candidate/evaluation/admission/promotion | AIOS-BACKED — `engine/aios_evolution.py` delegates to `AIOS.core.evolution` |

TRY does not reimplement AIOS authority or evolution rules. The adapter loads an explicitly pinned AIOS checkout through `AIOS_ROOT` and fails closed if the shared primitives are unavailable.

## Rule

Do not weaken this boundary to make a research iteration pass. New AI execution capabilities must enter through an explicit, controller-owned contract/capability boundary.


## AIOS repair reasoning bridge

TRY is the owner of the external reasoning credential. AIOS must not carry or call the Gemini credential directly.

The optional stdlib provider service is `python research/aios_repair_provider.py`.
It exposes only `POST /v1/repair/propose`, protected by `TRY_PROVIDER_TOKEN`.
The service accepts bounded failure evidence plus an immutable AIOS source snapshot and returns an untrusted schema-2 patch proposal.
It has no repository mutation capability and cannot grant AIOS authority.

The corresponding AIOS client is `core/try_repair_provider.py`. AIOS remains responsible for proposal validation, authority, mutation, testing, receipts, and PASS/FAIL determination.

Required separation:

`AIOS evidence -> TRY reasoning -> untrusted proposal -> AIOS authority -> mutation -> tests -> verification`

Never move `GEMINI_API_KEY` into AIOS. `TRY_REPAIR_PROVIDER_TOKEN` is only the bridge credential; it is not the external model credential.


### Runtime contract

The provider runtime is considered reachable only when `GET /healthz` returns `{"status":"READY","provider":"gemini","model":"..."}`. Health checks do not call Gemini. The repair endpoint remains `POST /v1/repair/propose` and requires the bridge token.

For CI deployment, expose only the provider URL and bridge token to AIOS: `TRY_REPAIR_PROVIDER_URL` and `TRY_REPAIR_PROVIDER_TOKEN`. The `GEMINI_API_KEY` remains a TRY-only runtime secret.
### GitHub credential ownership

Any GitHub credential used by the TRY-side reasoning/relay runtime belongs in TRY, not AIOS. In particular, `TRY_GITHUB_TOKEN` is a TRY repository secret/runtime variable and must never be copied into an AIOS workflow or `secrets.TRY_GITHUB_TOKEN`. AIOS only sends bounded repair evidence through the provider bridge; AIOS keeps its own repository-scoped `GITHUB_TOKEN` for its own CI operations.
