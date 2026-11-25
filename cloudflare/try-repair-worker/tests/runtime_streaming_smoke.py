import base64
import hashlib
import http.client
import json
import os
import time

HOST = os.environ.get("WORKER_HOST", "127.0.0.1")
PORT = int(os.environ.get("WORKER_PORT", "8787"))
TOKEN = os.environ.get("TRY_PROVIDER_TOKEN", "runtime-test-token")
MAX_BODY = 1_000_000

def request_chunked(path, chunks, method="POST"):
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.putrequest(method, path)
    connection.putheader("Authorization", f"Bearer {TOKEN}")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Transfer-Encoding", "chunked")
    connection.endheaders()
    try:
        for chunk in chunks:
            connection.send(f"{len(chunk):X}\r\n".encode("ascii"))
            connection.send(chunk)
            connection.send(b"\r\n")
        connection.send(b"0\r\n\r\n")
    except (BrokenPipeError, ConnectionResetError):
        # Expected when the Worker cancels an oversized incoming stream.
        pass
    response = connection.getresponse()
    payload = response.read()
    status = response.status
    connection.close()
    try:
        decoded = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        raise AssertionError(f"Worker returned non-JSON response: HTTP {status}")
    return status, decoded

def wait_for_worker():
    import urllib.error
    import urllib.request
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://{HOST}:{PORT}/healthz", timeout=2)
        except urllib.error.HTTPError:
            return
        except Exception:
            time.sleep(1)
            continue
        return
    raise AssertionError("Python Worker runtime did not start within 120 seconds")

def main():
    wait_for_worker()

    # /healthz must prove that the actual Workers/Pyodide WebCrypto bridge can
    # import the configured PKCS#8 key and produce a 64-byte Ed25519 signature.
    health = http.client.HTTPConnection(HOST, PORT, timeout=15)
    health.request("GET", "/healthz")
    health_response = health.getresponse()
    health_payload = json.loads(health_response.read())
    health.close()
    assert health_response.status == 503, (health_response.status, health_payload)
    assert health_payload.get("status") == "NOT_READY", health_payload
    assert health_payload.get("operation_receipt_signing_configured") is True, health_payload

    valid = {
        "request_id": "runtime-stream-valid",
        "repository": "yanhul/try",
        "sha": "a" * 40,
        "attempt": 1,
        "phase": "OBSERVE",
        "state": "WORKING",
    }
    encoded = json.dumps(valid, separators=(",", ":")).encode("utf-8")
    chunks = [encoded[i:i + 7] for i in range(0, len(encoded), 7)]
    status, payload = request_chunked("/v1/repair/checkpoint", chunks)
    assert status == 200, (status, payload)
    assert payload.get("persisted") is True, payload

    max_payload = {
        "request_id": "runtime-stream-max",
        "repository": "yanhul/try",
        "sha": "b" * 40,
        "attempt": 1,
        "phase": "OBSERVE",
        "state": "WORKING",
        "padding": "",
    }
    max_base = json.dumps(max_payload, separators=(",", ":")).encode("utf-8")
    max_payload["padding"] = "x" * (MAX_BODY - len(max_base))
    exact_body = json.dumps(max_payload, separators=(",", ":")).encode("utf-8")
    assert len(exact_body) == MAX_BODY, len(exact_body)
    chunks = [exact_body[i:i + 16384] for i in range(0, len(exact_body), 16384)]
    status, payload = request_chunked("/v1/repair/checkpoint", chunks)
    assert status == 200, (status, payload)
    assert payload.get("persisted") is True, payload
    oversized_id = "runtime-stream-oversized"
    oversized_prefix = (
        '{"request_id":"' + oversized_id + '","repository":"yanhul/try",'
        '"sha":"' + "a" * 40 + '","attempt":1,"phase":"OBSERVE",'
        '"state":"WORKING","padding":"'
    ).encode("utf-8")
    oversized = oversized_prefix + (b"x" * (MAX_BODY + 1 - len(oversized_prefix)))
    chunks = [oversized[i:i + 16384] for i in range(0, len(oversized), 16384)]
    status, payload = request_chunked("/v1/repair/checkpoint", chunks)
    assert status == 413, (status, payload)

    connection = http.client.HTTPConnection(HOST, PORT, timeout=15)
    connection.request(
        "GET", f"/v1/repair/checkpoint/{oversized_id}",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    response = connection.getresponse()
    missing_payload = json.loads(response.read())
    connection.close()
    assert response.status == 404, (response.status, missing_payload)

    # Exercise the actual Worker WebCrypto bridge (not the CPython test fallback).
    # No Gemini credential is configured, so this is a genuine pre-submission failure.
    request_id = "runtime-ed25519-receipt"
    operation = {
        "request_id": request_id, "repository": "yanhul/try", "sha": "c" * 40,
        "attempt": 1, "failure": {"kind": "runtime-signature-conformance"},
        "source_snapshot": {"core/runtime_smoke.py": "x = 1\n"},
    }
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request("POST", "/v1/repair/propose", body=json.dumps(operation), headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
    })
    response = connection.getresponse()
    proposal_payload = json.loads(response.read())
    connection.close()
    assert response.status == 409, (response.status, proposal_payload)

    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request("GET", f"/v1/repair/proposal/{request_id}", headers={
        "Authorization": f"Bearer {TOKEN}",
    })
    response = connection.getresponse()
    receipt_payload = json.loads(response.read())
    connection.close()
    assert response.status == 200, (response.status, receipt_payload)
    receipt = receipt_payload.get("operation_receipt", {})
    assert receipt.get("algorithm") == "Ed25519", receipt
    assert receipt.get("status") == "FAILED", receipt
    assert receipt.get("execution_state") == "NOT_SUBMITTED", receipt
    signed_fields = (
        "type", "issuer", "key_id", "receipt_id", "request_id", "request_digest",
        "repository", "sha", "attempt", "status", "execution_state", "failure_code",
        "proposal_digest", "issued_at", "expires_at", "algorithm",
    )
    signed = {key: receipt[key] for key in signed_fields}
    canonical = json.dumps(signed, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    with open("/tmp/try-operation-receipt-public-key.b64", encoding="ascii") as f:
        public_key = base64.b64decode(f.read().strip(), validate=True)
    signature = base64.b64decode(receipt["signature"], validate=True)
    Ed25519PublicKey.from_public_bytes(public_key).verify(signature, canonical)

    # Verify the very same Worker-generated receipt through AIOS's production
    # keyring/verifier, not only a standalone cryptography public-key check.
    from core.try_operation_receipt import (
        TryOperationReceiptKeyring,
        TryOperationReceiptError,
        verify_try_operation_receipt,
    )
    public_key_b64 = base64.b64encode(public_key).decode("ascii")
    keyring = TryOperationReceiptKeyring({
        "try.repair": {
            "public_key": public_key_b64,
            "key_id": "runtime-ed25519-test-v1",
            "scopes": ["try.operation.receipt.verify"],
            "revoked": False,
        }
    })
    request_digest = hashlib.sha256(json.dumps(
        operation, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()
    verified = verify_try_operation_receipt(
        receipt,
        request_id=request_id,
        request_digest=request_digest,
        repository=operation["repository"],
        sha=operation["sha"],
        attempt=operation["attempt"],
        keyring=keyring,
    )
    assert verified["status"] == "FAILED", verified
    assert verified["execution_state"] == "NOT_SUBMITTED", verified
    assert verified["proven_not_submitted"] is True, verified

    tampered = dict(receipt)
    tampered["signature"] = base64.b64encode(bytes(64)).decode("ascii")
    try:
        verify_try_operation_receipt(
            tampered,
            request_id=request_id,
            request_digest=request_digest,
            repository=operation["repository"],
            sha=operation["sha"],
            attempt=operation["attempt"],
            keyring=keyring,
        )
    except TryOperationReceiptError:
        pass
    else:
        raise AssertionError("AIOS verifier accepted a tampered Worker receipt")

    # Exercise the algorithm Durable Object through the real local Worker.
    grid = ["S..", ".#.", "..G"]
    spec = {"operation": "maze.shortest_path", "version": 1, "max_expansions": 100}
    algorithm_input = {"grid": grid}
    execution = {
        "contract_id": "CT-ALG-RUNTIME", "permit_id": "PM-ALG-RUNTIME",
        "execution_id": "EX-ALG-RUNTIME", "effect_id": "EF-ALG-RUNTIME",
        "dispatch_id": "DP-ALG-RUNTIME", "dispatch_digest": "c" * 64,
        "attempt_id": "EX-ALG-RUNTIME:attempt:1", "attempt_number": 1,
        "spec": spec, "input": algorithm_input,
    }
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request("POST", "/v1/algorithm/execute", body=json.dumps(execution), headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
    })
    response = connection.getresponse()
    algorithm_payload = json.loads(response.read())
    connection.close()
    assert response.status == 200, (response.status, algorithm_payload)
    assert algorithm_payload.get("status") == "COMPLETED", algorithm_payload
    artifact_bytes = base64.b64decode(algorithm_payload["artifact_b64"], validate=True)
    assert hashlib.sha256(artifact_bytes).hexdigest() == algorithm_payload["artifact_sha256"]
    artifact = json.loads(artifact_bytes)
    assert artifact["schema"] == "try.algorithm-artifact.v1"
    assert artifact["path"][0] == [0, 0] and artifact["path"][-1] == [2, 2]
    assert len(artifact["path"]) - 1 == 4

    # Verify the signed worker receipt with the AIOS P1 verifier and a test-only
    # deployment-pinned keyring; separately hash the exact persisted artifact.
    from core.algorithm_worker_receipt import (
        AlgorithmWorkerKeyring, verify_algorithm_worker_receipt,
    )
    from core.algorithm_worker_artifact import verify_algorithm_worker_artifact
    with open("/tmp/try-algorithm-receipt-public-key.b64", encoding="ascii") as f:
        algorithm_public_key = base64.b64decode(f.read().strip(), validate=True)
    algorithm_keyring = AlgorithmWorkerKeyring({
        "try.algorithm_executor": {
            "public_key": base64.b64encode(algorithm_public_key).decode("ascii"),
            "key_id": "runtime-algorithm-test-v1",
            "scopes": ["try.algorithm.execution.receipt.verify"],
            "revoked": False,
        }
    })
    executor_sha = hashlib.sha256(open("src/algorithm_runtime.py", "rb").read()).hexdigest()
    canonical = lambda value: json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    expected = {
        "contract_id": execution["contract_id"], "permit_id": execution["permit_id"],
        "execution_id": execution["execution_id"], "effect_id": execution["effect_id"],
        "dispatch_id": execution["dispatch_id"], "dispatch_digest": execution["dispatch_digest"],
        "attempt_id": execution["attempt_id"], "attempt_number": 1,
        "worker_id": "try-worker-runtime-test", "worker_build_sha256": "a" * 64,
        "executor_revision": "b" * 40, "executor_sha256": executor_sha,
        "spec_sha256": hashlib.sha256(canonical(spec)).hexdigest(),
        "input_sha256": hashlib.sha256(canonical(algorithm_input)).hexdigest(),
    }
    algorithm_receipt = algorithm_payload["operation_receipt"]
    verified_algorithm = verify_algorithm_worker_receipt(
        algorithm_receipt, expected=expected, keyring=algorithm_keyring
    )
    assert verified_algorithm["status"] == "INDEPENDENTLY_AUTHENTICATED", verified_algorithm
    assert verified_algorithm["retry_authorized"] is False
    assert verified_algorithm["promotion"] == "NOT_AUTHORIZED"
    independently_verified_artifact = verify_algorithm_worker_artifact(
        algorithm_receipt, artifact_bytes, expected=expected, grid=grid, spec=spec,
        expected_executor_revision="b" * 40, expected_executor_sha256=executor_sha,
        keyring=algorithm_keyring,
    )
    assert independently_verified_artifact["status"] == "INDEPENDENTLY_VERIFIED"
    assert independently_verified_artifact["oracle_distance"] == 4

    # Replay must return the same persisted artifact and receipt, not execute again.
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request("POST", "/v1/algorithm/execute", body=json.dumps(execution), headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
    })
    response = connection.getresponse()
    replay = json.loads(response.read())
    connection.close()
    assert response.status == 200 and replay["idempotent_replay"] is True, replay
    assert replay["artifact_b64"] == algorithm_payload["artifact_b64"]
    assert replay["operation_receipt"] == algorithm_receipt

    # A changed payload under the same execution identity must conflict.
    changed = dict(execution, dispatch_digest="d" * 64)
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request("POST", "/v1/algorithm/execute", body=json.dumps(changed), headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
    })
    response = connection.getresponse()
    conflict = json.loads(response.read())
    connection.close()
    assert response.status == 409, (response.status, conflict)

    algorithm_execution_result = {
        "status": independently_verified_artifact["status"],
        "artifact_sha256_verified": True,
        "durable_replay_same_receipt": True,
        "identity_conflict_rejected": True,
        "retry_authorized": False,
        "promotion": "NOT_AUTHORIZED",
    }

    print(json.dumps({
        "runtime": "cloudflare-python-workers-local",
        "readiness": "WebCrypto import+sign passed",
        "operation_receipt": "Worker WebCrypto -> AIOS verifier passed",
        "tamper_rejection": True,
        "algorithm_execution": algorithm_execution_result,
        "chunked_without_content_length": "accepted_and_persisted",
        "oversized_stream": "413_and_checkpoint_absent",
        "oversized_checkpoint_absent": True,
    }, sort_keys=True))

if __name__ == "__main__":
    main()
