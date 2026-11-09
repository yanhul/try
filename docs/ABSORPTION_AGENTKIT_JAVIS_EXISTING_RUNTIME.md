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

The proposed SQLite queue in the earlier draft PR #62 is a standalone queue with a callback-shaped verifier. It is not wired into TRY's research pipeline or AIOS's authoritative effect/attempt lifecycle. Therefore it is **not promoted as the canonical runtime** and must not be mistaken for completed absorption.

Required production adapter contract:
1. Receive an AIOS-authorized effect and exact attempt identity.
2. Submit to the selected TRY-owned runtime/provider.
3. Return a submission bound to the same `effect_id`, `attempt_id`, and provider.
4. Persist provider receipt/evidence references; never convert a worker observation directly into AIOS PASS.
5. On timeout/ambiguous side effect, preserve UNKNOWN; do not auto-requeue or invent a new attempt.
6. Retry only after AIOS has recorded explicit authorization and the contract's attempt budget allows it.

## 4. Existing workflow boundary and limitation

`.github/workflows/aios-central-conformance.yml` checks out a pinned AIOS revision and exercises the TRY-to-AIOS evolution adapter, then runs the research workload through the central runner. This is useful integration coverage, but it does not by itself prove that every provider effect is bound to a durable runtime receipt.

The exact AIOS pin is defined in that workflow. Any runtime adapter integration must update the pin deliberately and run against that exact revision; do not silently use whichever AIOS checkout happens to be on `main`.

## 5. Verification

Relevant existing tests:
- `tests/test_aios_boundary.py`
- `tests/test_aios_evolution_adapter.py`
- `tests/test_execution.py`
- `tests/test_research_pipeline.py`
- `tests/test_candidate_registration_lineage.py`

The prior PR #62 queue tests validate its isolated SQLite class and mocked verifier. They do not establish end-to-end integration with AIOS effect authority, the pinned AIOS revision, a real provider, or reconciliation. Keep the PR unmerged until a real adapter contract and cross-repository integration tests exist.

## 6. Source inventory limitation

The recoverable audit record names AgentKit and Javis OS as upstream pattern sources. It does not preserve the identity/URL of a third independent upstream repository; no third source is guessed or claimed as absorbed. No third-party source is copied into TRY.
