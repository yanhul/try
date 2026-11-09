# Absorption ledger: Coinbase AgentKit and Javis OS in TRY

Status: **selective ADAPT through existing AIOS authority and TRY provider boundaries; no parallel authority queue.**

TRY owns research/provider execution. AIOS owns contracts, permits, effect authorization, evidence verification and promotion.

## 1. Coinbase AgentKit — correct source classification

Upstream: https://github.com/coinbase/agentkit

Coinbase AgentKit is a wallet/on-chain action toolkit, not a general-purpose orchestration framework. Its Python source provides `ActionProvider`, typed `Action` metadata, Pydantic argument schemas, decorator registration and wallet/network compatibility checks.

**Potentially reusable design:** typed action declarations, explicit input schemas and provider capability/compatibility metadata at a future TRY provider adapter boundary.

**Rejected for this TRY scope:** Coinbase wallet/signing/on-chain transaction implementations, wallet credentials and the earlier claim that AgentKit supplied generic plan/delegation/orchestration patterns. No generic orchestration engine was established by the audited source. No AgentKit code is vendored by this PR.

TRY's current provider/research code remains authoritative for its own domain; AIOS capability registry and permit remain the authority gate.

## 2. Javis OS — source identity unresolved; prior attribution withdrawn

**Status: UNKNOWN.** The previously cited upstream URL `https://github.com/blogminhquy/javis-os` is not the Javis OS repository the project owner intended. All source-specific paths and implementation claims previously attributed to that URL are withdrawn.

GitHub search also surfaced `dodungvanphong/javis-os`, but its README points back to `blogminhquy/javis-os`; it is not accepted as the intended source. The correct repository and audited commit remain unidentified.

**Absorb decision: BLOCKED pending source identity.** Do not claim that Javis OS task-store, atomic-claim, lease/heartbeat, once-only ledger, checkpoint, MCP or memory patterns have been verified or absorbed into TRY.

The TRY/AIOS ownership boundary below remains valid independently of Javis OS:
- TRY owns research/provider execution and any future worker scheduler.
- AIOS owns effect authorization, immutable effect/attempt identity, receipt/evidence verification, UNKNOWN reconciliation and promotion.
- A worker lease timeout does not prove the provider did nothing. Ambiguous external effects remain UNKNOWN; no silent retry or invented attempt is allowed.

The standalone SQLite queue from superseded PR #62 remains closed/unmerged and is not treated as absorbed production code.

## 3. Existing TRY ↔ AIOS integration

| Concern | Existing implementation | Owner |
|---|---|---|
| Contract/permit/attestation boundary | `engine/aios_boundary.py` delegates to AIOS core | AIOS authority; TRY adapter |
| Candidate/evaluation/admission lifecycle | `engine/aios_evolution.py` delegates to `core.evolution` | AIOS admission; TRY research |
| Research execution | `aios/adapter.py`, `engine/research_pipeline.py` | TRY |
| Strategy identity/provenance | `engine/strategy_spec.py` | TRY |
| Governed effect/attempt | AIOS `core.effect_authority`, `core.durable_runtime` and `core.execution_lineage` | AIOS |

## 4. Cross-repository fixture verification

This PR adds `tests/test_aios_durable_runtime_integration.py` and `.github/workflows/aios-durable-runtime-integration.yml`. The workflow checks out AIOS at `e7e3ba1714e5d099470b8ab746fafd9ea0be726c` and exercises the actual AIOS contract, permit, effect and runtime APIs with a **fake provider and fake durable runtime**.

Run `42710343912` completed successfully. Its job log confirms:
- the pinned AIOS commit was checked out;
- 2 tests ran and passed;
- fixture provider submission was bound to the same `effect_id` and `attempt_id`;
- ambiguous provider timeout remained `UNKNOWN`, not `PASS`.

This is verified fixture-level boundary integration. It is not a live provider test, production scheduler/lease test, crash-recovery test or end-to-end reconciliation proof.

## 5. Decision and remaining production gap

The three-repository decision is **Coinbase AgentKit + Javis OS + AIOS**. AIOS is the destination control plane, not a third-party package to vendor into TRY. Google AI Pro automation is excluded.

The production gap remains: implement and test a TRY-owned runtime adapter that submits an AIOS-authorized effect, preserves exact effect/attempt/provider identity, persists provider receipt/evidence, and routes ambiguous outcomes into explicit AIOS reconciliation. No production scheduler or live external side effect is claimed here.
