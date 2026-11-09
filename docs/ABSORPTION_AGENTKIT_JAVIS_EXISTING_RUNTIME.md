# Absorption ledger: AgentKit and Javis OS patterns in TRY

Status: **ADAPT through existing AIOS boundaries and TRY adapters; do not add a second worker authority.**

TRY owns research and provider/runtime execution semantics. AIOS owns contracts, permits, effect authorization, evidence verification and promotion.

## 1. Existing canonical integration

| Concern | Existing implementation | Owner |
|---|---|---|
| Contract/permit/attestation validation | `engine/aios_boundary.py` delegates to AIOS core | AIOS authority; TRY adapter |
| Candidate/evaluation/admission lifecycle | `engine/aios_evolution.py` delegates to `core.evolution` | AIOS admission; TRY research |
| Research execution | `aios/adapter.py`, `engine/research_pipeline.py` | TRY |
| Strategy provenance and canonical identity | `engine/strategy_spec.py` | TRY |
| Governed execution state/effect/attempt | AIOS `core.orchestrator`, `core.durable_loop`, `core.effect_authority`, `core.durable_runtime` | AIOS |

## 2. AgentKit patterns

Adapt explicit task plans, role boundaries, scoped capability requests, handoff records and separate review/evidence roles through AIOS contracts/delegation. TRY may submit a research workload or candidate, but must not issue its own authority, widen a permit, or self-promote an evaluation.

Existing integration evidence:
- `tests/test_aios_evolution_adapter.py`
- `tests/test_aios_boundary.py`
- `.github/workflows/aios-central-conformance.yml`

## 3. Javis OS patterns

Adapt durable execution, idempotency, checkpoint/resume, lease ownership and ambiguous-outcome handling at the runtime boundary. Do not duplicate AIOS effect authority in a second TRY state machine.

The proposed SQLite queue in the earlier draft PR #62 was a standalone queue with a callback-shaped verifier. It was not wired into TRY's research pipeline or AIOS's authoritative effect/attempt lifecycle. PR #62 has therefore been closed unmerged and superseded; its branch is retained for reference. It must not be mistaken for completed absorption.

Required production adapter contract:
1. Receive an AIOS-authorized effect and exact attempt identity.
2. Submit to the selected TRY-owned runtime/provider.
3. Return a submission bound to the same `effect_id`, `attempt_id`, and provider.
4. Persist provider receipt/evidence references; never convert a worker observation directly into AIOS PASS.
5. On timeout/ambiguous side effect, preserve UNKNOWN; do not auto-requeue or invent a new attempt.
6. Retry only after AIOS has recorded explicit authorization and the contract's attempt budget allows it.

## 4. Cross-repository integration verification

TRY PR #63 adds `tests/test_aios_durable_runtime_integration.py` and `.github/workflows/aios-durable-runtime-integration.yml`. The workflow checks out AIOS at the explicit pin `e7e3ba1714e5d099470b8ab746fafd9ea0be726c` and runs two tests against real AIOS contract, permit, effect and runtime APIs:
- a successful fixture submission is bound to the exact AIOS effect and attempt;
- an ambiguous provider failure remains UNKNOWN, never PASS.

Run `42710343912` completed successfully; its log records 2 tests run and OK. This is verified boundary integration with a fake provider/runtime, not a live provider test or proof of production scheduling/reconciliation.

## 5. Existing workflow boundary

`.github/workflows/aios-central-conformance.yml` checks out a pinned AIOS revision and exercises the TRY-to-AIOS evolution adapter, then runs the research workload through the central runner. This is useful integration coverage, but it does not by itself prove that every provider effect is bound to a durable runtime receipt.

The exact AIOS pin is defined in each workflow. Any runtime adapter integration must update the pin deliberately and run against that exact revision; do not silently use whichever AIOS checkout happens to be on `main`.

## 6. Three-repository decision

The audited set was **AgentKit, Javis OS, and AIOS**:
- AgentKit supplies orchestration patterns, adapted through AIOS's existing orchestrator/delegation boundary.
- Javis OS supplies task-runtime/lifecycle patterns, adapted at the TRY execution boundary while AIOS retains effect authority.
- AIOS is the destination authority/evidence/verification/promotion control plane, not a third-party library to vendor into TRY.

Google AI Pro automation was explicitly excluded from this three-repository adaptation set.
