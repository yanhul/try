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
| Explicit generalized permit/capability object | TODO |
| General contract verifier reusable by other substrates | TODO |
| External-effect receipt/reconciliation layer | TODO |

The TODO items are deliberate: they must be promoted from proven AIOS primitives rather than reimplemented ad hoc here.

## Rule

Do not weaken this boundary to make a research iteration pass. New AI execution capabilities must enter through an explicit, controller-owned contract/capability boundary.
