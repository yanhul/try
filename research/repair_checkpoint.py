"""Client for TRY's Cloudflare Durable Object checkpoint API.

A checkpoint is durable bookkeeping only; AIOS still owns authority and proof.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_DIGEST = re.compile(r"^[0-9a-fA-F]{64}$")


class RepairCheckpointError(RuntimeError):
    pass


def persist_checkpoint(
    *, request_id: str, repository: str, sha: str, attempt: int,
    phase: str, state: str, evidence_digest: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Persist one idempotent state transition or fail closed."""
    base_url = os.environ.get("TRY_REPAIR_PROVIDER_URL", "").strip().rstrip("/")
    token = os.environ.get("TRY_REPAIR_PROVIDER_TOKEN", "").strip()
    if not base_url or not token:
        raise RepairCheckpointError("checkpoint_provider_not_configured")
    if not base_url.startswith("https://"):
        raise RepairCheckpointError("checkpoint_provider_must_use_https")
    if not isinstance(request_id, str) or not request_id.strip():
        raise RepairCheckpointError("checkpoint_request_id_invalid")
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise RepairCheckpointError("checkpoint_repository_invalid")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise RepairCheckpointError("checkpoint_sha_invalid")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or not 1 <= attempt <= 20:
        raise RepairCheckpointError("checkpoint_attempt_invalid")
    if phase not in {"OBSERVE", "DECIDE", "PROPOSE", "VERIFY", "PERSIST", "RESUME"}:
        raise RepairCheckpointError("checkpoint_phase_invalid")
    if state not in {"WORKING", "BLOCKED", "DONE"}:
        raise RepairCheckpointError("checkpoint_state_invalid")
    if evidence_digest is not None and (not isinstance(evidence_digest, str) or not _DIGEST.fullmatch(evidence_digest)):
        raise RepairCheckpointError("checkpoint_evidence_digest_invalid")
    if state == "DONE" and (phase != "PERSIST" or not evidence_digest):
        raise RepairCheckpointError("checkpoint_done_requires_persisted_evidence")

    payload = {
        "request_id": request_id, "repository": repository, "sha": sha.lower(),
        "attempt": attempt, "phase": phase, "state": state,
        "evidence_digest": evidence_digest.lower() if evidence_digest else None,
        "reason": reason,
    }
    request = urllib.request.Request(
        base_url + "/v1/repair/checkpoint",
        data=json.dumps(payload, sort_keys=True).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    for retry in range(2):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
                status = response.status
            if status != 200 or not isinstance(result, dict) or not result.get("persisted"):
                raise RepairCheckpointError(f"checkpoint_rejected:{status}:{str(result)[:500]}")
            return result
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            last_error = RepairCheckpointError(f"checkpoint_http_{exc.code}:{detail}")
            if exc.code not in {429, 500, 502, 503, 504} or retry == 1:
                break
        except (OSError, TimeoutError, ValueError) as exc:
            last_error = RepairCheckpointError(f"checkpoint_transport_or_protocol:{type(exc).__name__}:{exc}")
            if retry == 1:
                break
        if retry == 0:
            time.sleep(1)
    raise last_error or RepairCheckpointError("checkpoint_unknown_failure")
