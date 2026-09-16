# Governance Kernel

The research runtime follows one rule: **a documented procedure is not a control unless the runtime can enforce it**.

## Required path

`event -> state/provenance -> transition -> permit -> effect -> dispatch -> execute_attempt -> receipt -> verify -> persist -> resume`

## Hard invariants

1. `REPAIR_FAIL -> controller invocation = 0`.
2. `HOLD | BLOCKED | UNKNOWN -> no dispatch/execute`.
3. `EXECUTE -> predecessor + evidence + authority + lineage`.
4. `OOS_FAIL -> explicit oos_failed_bc`.
5. `OOS migration -> target == recorded oos_failed_bc`.
6. `campaign_terminal=false -> campaign_terminal_reason=null`.
7. Invalid state is rejected before persistence.

## Enforcement rule

Lifecycle code may request a `Permit`, but only the governance kernel may grant it. Executors must call `require_permit()` and must not accept a boolean or free-form lifecycle status as authorization.

CI must test negative paths, not only successful transitions. A passing component test is insufficient when a boundary can still bypass the contract.

Formal/state-model checks may strengthen the contract, but they do not authorize runtime behavior; runtime authorization remains in the kernel.
