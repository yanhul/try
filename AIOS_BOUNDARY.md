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
