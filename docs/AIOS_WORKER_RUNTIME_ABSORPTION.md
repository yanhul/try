# TRY worker runtime absorption

Decision: ADAPT, not fork. The queue is TRY-owned and delegates authorization to
an injected AIOS contract/permit verifier before enqueue, claim, heartbeat,
checkpoint, observation and UNKNOWN transition.

Adapted Javis OS patterns: SQLite queue, idempotency key, atomic claim, lease,
heartbeat, monotonic checkpoint and resumable job identity.

Safety boundary:
- Expired CLAIMED/RUNNING leases become UNKNOWN, never silently QUEUED.
- UNKNOWN has no automatic retry path; another attempt needs a separately
  authorized AIOS operation/permit and explicit decision.
- OBSERVED is a worker observation, not AIOS PASS or research acceptance.
- No plugin loading, shell execution, secret handling, policy mutation or
  promotion authority is implemented here.

TRY retains its IS -> validation -> OOS research separation. AIOS remains the
sole authority for verification and promotion.
