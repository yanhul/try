import base64
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

    print(json.dumps({
        "runtime": "cloudflare-python-workers-local",
        "operation_receipt": "WebCrypto Ed25519 signature verified",
        "chunked_without_content_length": "accepted_and_persisted",
        "oversized_stream": "413_and_checkpoint_absent",
        "oversized_checkpoint_absent": True,
    }, sort_keys=True))

if __name__ == "__main__":
    main()
