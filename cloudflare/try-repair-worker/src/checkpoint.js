const PHASES = ["OBSERVE", "DECIDE", "PROPOSE", "VERIFY", "PERSIST", "RESUME"];
const STATES = ["WORKING", "BLOCKED", "DONE"];
const DIGEST = /^[0-9a-f]{64}$/i;
const SHA = /^[0-9a-f]{40}$/i;

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

export class RepairCheckpoint {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.storage = ctx.storage;
  }

  async fetch(request) {
    if (request.method === "GET") {
      const record = await this.storage.get("record");
      return record ? json(record) : json({ error: "checkpoint_not_found" }, 404);
    }
    if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405);

    let input;
    try { input = await request.json(); } catch { return json({ error: "invalid_json" }, 400); }
    if (!input || typeof input !== "object" || Array.isArray(input)) return json({ error: "invalid_record" }, 400);

    const { request_id, repository, sha, attempt, phase, state, evidence_digest, reason } = input;
    if (typeof request_id !== "string" || !/^[A-Za-z0-9._:-]{1,160}$/.test(request_id)) return json({ error: "request_id_invalid" }, 400);
    if (typeof repository !== "string" || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) return json({ error: "repository_invalid" }, 400);
    if (typeof sha !== "string" || !SHA.test(sha)) return json({ error: "sha_invalid" }, 400);
    if (!Number.isInteger(attempt) || attempt < 1 || attempt > 20) return json({ error: "attempt_invalid" }, 400);
    if (!PHASES.includes(phase) || !STATES.includes(state)) return json({ error: "phase_or_state_invalid" }, 400);
    if (evidence_digest !== undefined && (typeof evidence_digest !== "string" || !DIGEST.test(evidence_digest))) return json({ error: "evidence_digest_invalid" }, 400);
    if (state === "DONE" && (phase !== "PERSIST" || !evidence_digest)) return json({ error: "done_requires_persisted_evidence_digest" }, 409);
    if (state === "BLOCKED" && (typeof reason !== "string" || !reason.trim())) return json({ error: "blocked_requires_reason" }, 400);

    return await this.ctx.blockConcurrencyWhile(async () => {
      const prior = await this.storage.get("record");
      if (!prior) {
        if (attempt !== 1 || phase !== "OBSERVE" || state !== "WORKING") return json({ error: "initial_checkpoint_must_start_at_observe_attempt_1" }, 409);
      } else {
        if (prior.request_id !== request_id || prior.repository !== repository || prior.sha !== sha) return json({ error: "checkpoint_identity_conflict" }, 409);
        if (prior.state === "DONE") return json({ error: "checkpoint_terminal" }, 409);
        if (attempt < prior.attempt || attempt > prior.attempt + 1) return json({ error: "attempt_not_monotonic" }, 409);
        if (attempt === prior.attempt + 1 && !(prior.state === "BLOCKED" && phase === "RESUME" && state === "WORKING")) return json({ error: "retry_requires_blocked_prior_and_resume_phase" }, 409);
        if (attempt === prior.attempt) {
          const next = {
            OBSERVE: ["DECIDE", "BLOCKED"],
            DECIDE: ["PROPOSE", "BLOCKED"],
            PROPOSE: ["VERIFY", "BLOCKED"],
            VERIFY: ["PERSIST", "BLOCKED"],
            PERSIST: ["RESUME", "BLOCKED", "DONE"],
            RESUME: ["OBSERVE", "BLOCKED"],
          };
          if (phase !== prior.phase && !next[prior.phase].includes(phase)) return json({ error: "invalid_phase_transition" }, 409);
          if (prior.state === "BLOCKED" && !(phase === "RESUME" && state === "WORKING")) return json({ error: "blocked_checkpoint_requires_resume" }, 409);
          if (state === "DONE" && prior.phase !== "PERSIST" && phase !== "PERSIST") return json({ error: "done_requires_persist_phase" }, 409);
        }
      }

      const record = {
        schema: 1, request_id, repository, sha: sha.toLowerCase(), attempt,
        phase, state, evidence_digest: evidence_digest || null,
        reason: state === "BLOCKED" ? reason.slice(0, 1000) : null,
        version: (prior?.version || 0) + 1,
      };
      await this.storage.put("record", record);
      return json({ ...record, persisted: true }, 200);
    });
  }
}
