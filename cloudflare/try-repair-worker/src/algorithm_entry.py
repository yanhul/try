"""Cloudflare Worker entrypoint for the bounded algorithm execution lifecycle.

The base repair provider remains unchanged. Algorithm execution is a separate,
closed-set route backed by its own Durable Object namespace.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

from workers import DurableObject, Response

from entry import (
    Default as RepairDefault,
    RepairCheckpoint as RepairCheckpoint,
    _algorithm_execution_receipt,
    _canonical_json,
    _read_bounded_json,
    _valid_operation_receipt_private_key,
)
from algorithm_runtime import execute

MAX_ARTIFACT_BYTES = 256_000
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _executor_source_sha256() -> str:
    return hashlib.sha256(Path(__import__("algorithm_runtime").__file__).read_bytes()).hexdigest()


def _algorithm_readiness(env) -> tuple[bool, str]:
    if not _valid_operation_receipt_private_key(getattr(env, "TRY_ALGORITHM_RECEIPT_PRIVATE_KEY", "")):
        return False, "algorithm_receipt_signing_not_configured"
    for name in ("TRY_ALGORITHM_RECEIPT_KEY_ID", "TRY_ALGORITHM_WORKER_ID"):
        value = getattr(env, name, "")
        if not isinstance(value, str) or not value.strip():
            return False, "algorithm_worker_identity_not_configured"
    worker_build = getattr(env, "TRY_ALGORITHM_WORKER_BUILD_SHA256", "")
    if not isinstance(worker_build, str) or not _HEX64_RE.fullmatch(worker_build):
        return False, "algorithm_worker_build_not_configured"
    revision = getattr(env, "TRY_ALGORITHM_EXECUTOR_REVISION", "")
    if not isinstance(revision, str) or not _SHA_RE.fullmatch(revision):
        return False, "algorithm_executor_revision_not_configured"
    pinned_source = getattr(env, "TRY_ALGORITHM_EXECUTOR_SHA256", "")
    if not isinstance(pinned_source, str) or not _HEX64_RE.fullmatch(pinned_source):
        return False, "algorithm_executor_digest_not_configured"
    if pinned_source != _executor_source_sha256():
        return False, "algorithm_executor_digest_mismatch"
    return True, "READY"


def _validate_execution_request(body: dict) -> tuple[dict, str]:
    required = {
        "contract_id", "permit_id", "execution_id", "effect_id", "dispatch_id",
        "dispatch_digest", "attempt_id", "attempt_number", "spec", "input",
    }
    if not isinstance(body, dict) or set(body) != required:
        raise ValueError("algorithm_request_fields_invalid")
    for field in ("contract_id", "permit_id", "execution_id", "effect_id", "dispatch_id", "attempt_id"):
        value = body[field]
        if not isinstance(value, str) or not _ID_RE.fullmatch(value):
            raise ValueError("algorithm_request_identity_invalid")
    if not isinstance(body["dispatch_digest"], str) or not _HEX64_RE.fullmatch(body["dispatch_digest"]):
        raise ValueError("algorithm_dispatch_digest_invalid")
    number = body["attempt_number"]
    if isinstance(number, bool) or not isinstance(number, int) or number != 1:
        raise ValueError("algorithm_attempt_invalid")
    # Runtime validates exact spec/input schemas and resource bounds.
    runtime_input = {"spec": body["spec"], "input": body["input"]}
    request_digest = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
    return runtime_input, request_digest


class AlgorithmExecutionStore(DurableObject):
    """One immutable execution identity; dispatch is persisted before computation."""
    def __init__(self, ctx, env):
        self.ctx = ctx
        self.env = env
        self._lock = asyncio.Lock()

    async def read_execution(self):
        record = await self.ctx.storage.get("record")
        artifact_b64 = await self.ctx.storage.get("artifact_b64")
        return record, artifact_b64

    async def execute_once(self, body: dict):
        runtime_input, request_digest = _validate_execution_request(body)
        async with self._lock:
            prior = await self.ctx.storage.get("record")
            if prior is not None:
                if prior.get("request_digest") != request_digest:
                    return {"status": "CONFLICT", "error": "execution_identity_conflict"}
                if prior.get("status") == "COMPLETED":
                    artifact_b64 = await self.ctx.storage.get("artifact_b64")
                    return {"status": "COMPLETED", "record": prior,
                            "artifact_b64": artifact_b64, "idempotent_replay": True}
                return {"status": "UNKNOWN", "record": prior,
                        "artifact_b64": None, "idempotent_replay": True}

            # These fields are pinned from deployment configuration, never caller input.
            executor_revision = self.env.TRY_ALGORITHM_EXECUTOR_REVISION
            executor_sha256 = _executor_source_sha256()
            record = {
                "schema": 1,
                "contract_id": body["contract_id"], "permit_id": body["permit_id"],
                "execution_id": body["execution_id"], "effect_id": body["effect_id"],
                "dispatch_id": body["dispatch_id"], "dispatch_digest": body["dispatch_digest"],
                "attempt_id": body["attempt_id"], "attempt_number": body["attempt_number"],
                "executor_revision": executor_revision, "executor_sha256": executor_sha256,
                "spec_sha256": hashlib.sha256(_canonical_json(runtime_input["spec"]).encode("utf-8")).hexdigest(),
                "input_sha256": hashlib.sha256(_canonical_json(runtime_input["input"]).encode("utf-8")).hexdigest(),
                "status": "UNKNOWN", "execution_state": "IN_PROGRESS_OR_AMBIGUOUS",
                "request_digest": request_digest,
            }
            # A crash after this write is permanently UNKNOWN for this execution_id.
            await self.ctx.storage.put("record", record)

            result = execute(runtime_input)
            artifact_bytes = result["artifact_bytes"]
            if len(artifact_bytes) > MAX_ARTIFACT_BYTES:
                raise ValueError("algorithm_artifact_too_large")
            artifact_b64 = base64.b64encode(artifact_bytes).decode("ascii")
            # Artifact bytes are durable before terminal COMPLETED is written.
            await self.ctx.storage.put("artifact_b64", artifact_b64)
            completed = {
                **record,
                "spec_sha256": result["spec_sha256"],
                "input_sha256": result["input_sha256"],
                "artifact_sha256": result["artifact_sha256"],
                "output_sha256": result["output_sha256"],
                "status": "COMPLETED", "execution_state": "COMPLETED",
            }
            receipt = await _algorithm_execution_receipt(completed, self.env)
            completed["receipt"] = receipt
            await self.ctx.storage.put("record", completed)
            return {"status": "COMPLETED", "record": completed,
                    "artifact_b64": artifact_b64, "idempotent_replay": False}


class Default(RepairDefault):
    async def fetch(self, request):
        path = urlparse(request.url).path
        if path not in ("/v1/algorithm/execute",) and not path.startswith("/v1/algorithm/execution/"):
            return await super().fetch(request)

        expected = getattr(self.env, "TRY_PROVIDER_TOKEN", "")
        supplied = request.headers.get("Authorization", "")
        if not expected or supplied != f"Bearer {expected}":
            return Response.json({"error": "unauthorized"}, status=401)

        ready, reason = _algorithm_readiness(self.env)
        if not ready:
            return Response.json({"error": reason}, status=503)
        namespace = getattr(self.env, "ALGORITHM_EXECUTIONS", None)
        if namespace is None:
            return Response.json({"error": "algorithm_execution_store_not_configured"}, status=503)

        if request.method == "POST" and path == "/v1/algorithm/execute":
            try:
                body = await _read_bounded_json(request)
                runtime_input, _ = _validate_execution_request(body)
                stub = namespace.get(namespace.idFromName(body["execution_id"]))
                result = await stub.execute_once(body)
                if result["status"] == "CONFLICT":
                    return Response.json({"error": result["error"]}, status=409)
                record = result["record"]
                if result["status"] == "UNKNOWN":
                    receipt = await _algorithm_execution_receipt(record, self.env)
                    return Response.json({
                        "status": "UNKNOWN", "retry_allowed": False,
                        "operation_receipt": receipt,
                    }, status=202)
                return Response.json({
                    "status": "COMPLETED", "retry_allowed": False,
                    "artifact_b64": result["artifact_b64"],
                    "artifact_sha256": record["artifact_sha256"],
                    "operation_receipt": record["receipt"],
                    "idempotent_replay": result["idempotent_replay"],
                }, status=200)
            except ValueError as exc:
                reason = str(exc)
                status = 413 if reason in {"body_too_large", "body_size_mismatch"} else 400
                return Response.json({"error": reason}, status=status)
            except Exception as exc:
                # A post-dispatch failure must be reconciled from Durable Object
                # state. Return a signed UNKNOWN when the durable record exists.
                try:
                    if "stub" in locals():
                        record, _artifact_b64 = await stub.read_execution()
                        if record is not None:
                            receipt = await _algorithm_execution_receipt(record, self.env)
                            return Response.json({
                                "status": "UNKNOWN", "retry_allowed": False,
                                "operation_receipt": receipt,
                            }, status=202)
                except Exception:
                    pass
                # If storage itself is unavailable, do not fabricate a receipt.
                return Response.json({
                    "status": "UNKNOWN", "retry_allowed": False,
                    "receipt_unavailable": True, "reason": type(exc).__name__,
                }, status=503)

        prefix = "/v1/algorithm/execution/"
        if request.method == "GET" and path.startswith(prefix):
            execution_id = path[len(prefix):]
            if not _ID_RE.fullmatch(execution_id):
                return Response.json({"error": "execution_id_invalid"}, status=400)
            try:
                stub = namespace.get(namespace.idFromName(execution_id))
                record, artifact_b64 = await stub.read_execution()
                if record is None:
                    return Response.json({"error": "execution_not_found"}, status=404)
                if record.get("status") == "COMPLETED" and isinstance(artifact_b64, str):
                    return Response.json({
                        "status": "COMPLETED", "artifact_b64": artifact_b64,
                        "artifact_sha256": record["artifact_sha256"],
                        "operation_receipt": record["receipt"],
                    }, status=200)
                receipt = await _algorithm_execution_receipt(record, self.env)
                return Response.json({
                    "status": "UNKNOWN", "retry_allowed": False,
                    "operation_receipt": receipt,
                }, status=202)
            except Exception as exc:
                return Response.json({"error": "algorithm_execution_read_failed",
                                      "reason": type(exc).__name__}, status=503)
        return Response.json({"error": "not_found"}, status=404)
