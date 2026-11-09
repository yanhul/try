# Absorption ledger: Coinbase AgentKit and Javis OS in TRY

Status: **selective ADAPT through existing AIOS authority and TRY provider boundaries; no parallel authority queue.**

TRY owns research/provider execution. AIOS owns contracts, permits, effect authorization, evidence verification and promotion.

## 1. Coinbase AgentKit — correct source classification

Upstream: https://github.com/coinbase/agentkit

Coinbase AgentKit is a wallet/on-chain action toolkit, not a general-purpose orchestration framework. Its Python source provides `ActionProvider`, typed `Action` metadata, Pydantic argument schemas, decorator registration and wallet/network compatibility checks.

**Potentially reusable design:** typed action declarations, explicit input schemas and provider capability/compatibility metadata at a future TRY provider adapter boundary.

**Rejected for this TRY scope:** Coinbase wallet/signing/on-chain transaction implementations, wallet credentials and the earlier claim that AgentKit supplied generic plan/delegation/orchestration patterns. No generic orchestration engine was established by the audited source. No AgentKit code is vendored by this PR.

TRY's current provider/research code remains authoritative for its own domain; AIOS capability registry and permit remain the authority gate.

## 2. Javis OS — Nguyễn Minh Quý fork, pinned snapshot audit

**Source identity verified:** https://github.com/minhhoan1007/javis-os  
**Audited fork HEAD:** `8a38217d9f6e9c54e83898fb3242a6fd5c4ca6d5` (2026-09-07).  
**Repository metadata:** description `Nguyễn Minh Quý`; fork of `blogminhquy/javis-os`. This fork is a historical snapshot, not a separate upstream; its recorded HEAD is 967 commits behind upstream main observed on 2026-11-09. The findings below are pinned to the fork commit, not current upstream.

### Verified implementation
- `server/task_store.py`: SQLite/WAL queue, `BEGIN IMMEDIATE`, status-guarded claim, per-brain unique enqueue idempotency key, task/run/event rows.
- `server/tasks.py`: asyncio dispatcher and workers; 90-second lease, 20-second heartbeat, 5-second dispatcher interval; bounded worker pool and stale-worker housekeeping.
- `reclaim_stale` requeues expired tasks as `ready` and marks the old run `stale`.
- `tests/python/test_tasks_autonomous.py` tests legacy migration/snapshot, compare-and-set claim, dependency promotion and dispatcher lifecycle. Its claim test is sequential against one TaskStore; it does not establish multiprocess race safety or external-effect crash safety.

### Not established
The pinned fork contains no tracked `once_ledger.py`, independent workflow-run store or checkpoint subsystem. No exactly-once guarantee, provider receipt reconciliation or crash-safe external-effect retry is established.

### Adapt / reject
- **Adapt as scheduler mechanics only:** bounded dispatcher, transactional claim, run/event history, heartbeat and dependency promotion.
- **Reject as authority semantics:** stale lease recovery automatically requeues a task. A worker may have completed an external action before dying; requeue can duplicate that action. Lease expiry alone is not proof of non-execution.
- Enqueue idempotency is not provider-effect idempotency. The per-brain key deduplicates task creation; title coalescing is only queue behavior.
- TRY may own scheduling and provider execution, but every external side effect must retain AIOS-issued effect/attempt identity and receipt lineage. Ambiguous outcomes remain UNKNOWN and require explicit reconciliation; no silent retry.

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
