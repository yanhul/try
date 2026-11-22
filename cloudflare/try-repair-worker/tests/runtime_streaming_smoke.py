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
    print(json.dumps({
        "runtime": "cloudflare-python-workers-local",
        "chunked_without_content_length": "accepted_and_persisted",
        "oversized_stream": "413_and_cancelled_before_storage",
        "oversized_checkpoint_absent": True,
    }, sort_keys=True))

if __name__ == "__main__":
    main()
