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


## 6. Corrected upstream audit (distinct from the Minh Quý fork)

The fork-only findings in section 2 remain scoped to the pinned fork. This section records a separate direct audit of upstream:

- Upstream: https://github.com/blogminhquy/javis-os
- Pinned upstream ref: `f1bc4c3e52b4bda71d229e780da3b23a3ededa60` (main, observed 2026-11-10).

Directly inspected upstream modules:
- `server/once_ledger.py`: per-job/tool/normalized-arguments fingerprint ledger with STARTED, SUCCEEDED, FAILED and UNKNOWN. Prior success is reused; ambiguous timeout/connection loss and interrupted prior-process calls become UNKNOWN rather than silently re-running. This is a local application guard, not provider-enforced exactly-once.
- `server/workflow_runs.py`: separate SQLite WAL workflow-run history store, not the Kanban task queue.
- `server/workflow_runtime.py`: workflow graph with checkpoint/resume, completed-node preservation, user approval for write nodes, and pinned nested-workflow revisions. Policy defaults are off/zero allocation/writes disabled; code presence is not proof of rollout.
- `server/context_runtime.py`: capability lease, invocation, evidence, checkpoint and resource-lock tables; stale RUNNING writes become UNKNOWN after restart and keep their resource lock until reconciliation.
- `server/capability_executor.py`: schema/scope validation, capability revision pinning, one-use lease claim and evidence persistence.
- `server/incident_desk.py` and `server/sentinel.py`: bounded incident retry gate and read-only grouped health scan.

### Updated integration decision
- AIOS already supplies the authority/effect boundary: `core/effect_authority.py`, `core/runtime.py` and `core/durable_runtime.py` bind contract/permit, effect, attempt and provider identity; ambiguous provider outcomes remain UNKNOWN; retry requires explicit authorization and contract budget.
- TRY should consume AIOS's `DurableRuntime` protocol for scheduler handoff. Javis queue claim/worker/heartbeat/run-history/dependency patterns may inform a future TRY scheduler adapter. Do not copy Javis once-ledger or write ledger as a second authority store.
- Javis checkpoint state may resume workflow computation, but it must never independently promote an external effect to success. The authoritative effect/attempt/receipt remains in AIOS.
- No Javis queue is vendored or deployed by this PR. Current evidence is fixture-level AIOS runtime integration, not production scheduler wiring or live provider execution.

This is source-code inspection at the pinned upstream ref; the Javis upstream test suite was not run.


## 7. Initial TRY scheduler adapter implementation (2026-11-10)

The branch now includes `engine/aios_durable_runtime.py`, a TRY-owned SQLite/WAL handoff adapter implementing the AIOS `DurableRuntime` protocol:
- idempotent submit bound to the exact AIOS effect, attempt and provider;
- transactional worker claim using `BEGIN IMMEDIATE`;
- worker-owned lease heartbeat;
- expired leases transition to scheduler `UNKNOWN`, never automatic requeue;
- resume is rejected after claim/ambiguity; retry requires a new AIOS attempt identity;
- scheduler terminal mirroring accepts only AIOS observed terminal states and creates no evidence itself.

Tests are in `tests/test_try_durable_runtime_adapter.py`. Workflow `TRY AIOS Durable Runtime Integration` run **42729176618** completed successfully on commit `9f86e955fe142de2ffd117d052992c0480b609aa`. The job log records **10 tests passed**: 2 AIOS boundary fixtures and 8 adapter tests, including concurrent worker claim and expired-lease UNKNOWN behavior.

### Explicit limits

This is an implemented scheduler persistence/lease primitive, not a fully deployed worker runtime:
- no long-running worker loop or service wiring yet;
- no automatic bridge from scheduler lease expiry into AIOS `effect_authority.unknown`; orchestration must reconcile the returned effect/attempt pair against AIOS before any retry;
- no real-provider crash-window test (provider acted, process died before receipt persistence);
- no live provider action or production filesystem/multiprocess deployment validation.

Therefore CI PASS proves these 10 fixture/unit tests only. It does not prove production readiness, exactly-once external effects, or completed end-to-end reconciliation.

## 8. Durable-runtime integration blockers closed (2026-11-10)

Implements the handoff in PR #63 comment 6763326374.

### Worker execution path (`engine/aios_durable_worker.py`)
`AiosDurableWorker.run_once()` is the only TRY code path that reaches a provider:
1. `claim()` — SQLite scheduling snapshot only.
2. `authoritative_dispatch()` (`engine/aios_authority_reader.py`) — reloads the effect-of-record via AIOS public APIs (`core.mutation.recover_pending`, `core.external_effect.load_effects`, `core.authority.authorize/load_contract/load_permit`) and requires state `DISPATCHED` with exact effect_id / attempt_id / attempt / provider / actor / contract_id / permit_id / effect_type binding, a live contract+permit, provider capability and attempt budget. Missing, unreadable, stale, terminal, UNKNOWN or mismatched authority fails closed to queue `UNKNOWN` without calling the provider.
3. `heartbeat()` — lease must still be owned; otherwise the provider is not called.
4. `core.runtime.execute_attempt()` — AIOS calls the provider and persists the observation or UNKNOWN.
5. `mirror_verified_terminal()` — re-reads AIOS; never trusts the return value.

`enqueue_dispatched()` / `enqueue_retry()` create/dispatch through AIOS (`create_effect`, `dispatch`, `retry_dispatch`) without calling the provider. Retry requires AIOS `UNKNOWN`, the AIOS attempt budget, and the scheduler gate (previous attempt row `UNKNOWN`, no live/terminal row); the gate is checked before `retry_dispatch` so a refused retry does not consume an AIOS attempt.

### Receipt-backed terminal mirroring
`mark_aios_terminal(state=...)` was removed. `mirror_verified_terminal()` takes no state: it requires an AIOS `OBSERVED_*` effect whose `provider_observation` binds effect/attempt/provider, has a `provider_operation_id`, and carries a digest-valid AIOS `EvidenceRecord` with matching provider and `run_id == attempt_id`. The verified digest is stored in `aios_receipt_json`. On failure the row is left non-terminal. A CLAIMED row can be mirrored only by its owning worker.

### Proven by tests (`tests/test_aios_durable_runtime_worker.py`, real SQLite adapter + real AIOS file store)
- AIOS `execute()` with `TrySQLiteDurableRuntime`: persisted handoff identity/readback; a later worker claim does not re-execute and mirrors the verified receipt.
- Worker path: success, observed failure, provider ambiguity, AIOS persistence failure after provider call → UNKNOWN.
- Pre-execution rejection without provider call: AIOS UNKNOWN, superseded attempt (AIOS DISPATCHED for attempt 2, row attempt 1), deleted effect, corrupt effect JSON, revoked permit, tampered attempt/contract/permit/actor/provider, worker actor mismatch.
- Forged terminal: AIOS non-terminal, bad evidence digest, evidence bound to another attempt, other worker mirroring a claimed row.
- Lease: expired lease → UNKNOWN, no requeue, retry refused while AIOS still DISPATCHED; lease lost between authority read and provider call → provider skipped.
- Retry: explicit bounded retry succeeds; retry beyond `max_attempts` refused; scheduler gate refuses without consuming an AIOS attempt.
- Crash window: a real child process `os._exit(137)` after a fsync'd local side effect, before the AIOS receipt. Result: AIOS stays DISPATCHED, no terminal mirror, no automatic re-execution, retry refused until an explicit AIOS `unknown()` decision.
- Mutation check (local): disabling the DISPATCHED check, evidence digest check, worker authority read, or lease→UNKNOWN each makes tests fail.

### Not proven — remaining limitations
- **Not exactly-once.** The crash test shows an explicitly authorized retry after a crash duplicates a non-idempotent side effect (asserted). Real providers need idempotency keyed on effect_id/attempt_id.
- TOCTOU: AIOS has no compare-and-set on `execute_attempt`; between the authority read and the provider call another AIOS writer could change the effect. The window is minimized, not closed.
- The provider fixture is a local ledger file, not a live external provider.
- Multiprocess: one real child-process crash test only; no proof on the deployment filesystem, no concurrent multi-host workers, no NFS.
- No service loop, deployment config, or automated reconciliation for rows/effects left UNKNOWN or DISPATCHED after a crash; that requires an operator/AIOS decision.
- `load_effects` scans the whole effects directory per read (O(n)); acceptable for this slice, not for large stores.
