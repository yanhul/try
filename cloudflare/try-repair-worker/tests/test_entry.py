import asyncio
import importlib
import json
import sys
import types
import unittest


class _FakeChunk:
    def __init__(self, data):
        self._data = bytes(data)
        self.byteLength = len(self._data)
    def to_py(self):
        return memoryview(self._data)

class _FakeReadResult:
    def __init__(self, done, value=None):
        self.done = done
        self.value = value

class _FakeReader:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.read_count = 0
        self.cancelled = False
        self.released = False
    async def read(self):
        self.read_count += 1
        if not self._chunks:
            return _FakeReadResult(True)
        return _FakeReadResult(False, _FakeChunk(self._chunks.pop(0)))
    async def cancel(self, reason=None):
        self.cancelled = True
        self._chunks.clear()
    def releaseLock(self):
        self.released = True

class _FakeStream:
    def __init__(self, chunks):
        self.reader = _FakeReader(chunks)
    def getReader(self):
        return self.reader

class _Response:
    def __init__(self, status, payload=None, detail=""):
        self.status = status
        self.ok = 200 <= status < 300
        self._payload = payload
        self._detail = detail

    async def json(self):
        return self._payload

    async def text(self):
        return self._detail


class _FakeEntrypoint:
    pass


class _FakeResponse:
    @staticmethod
    def json(payload, status=200, headers=None):
        return payload


sys.modules["workers"] = types.SimpleNamespace(
    WorkerEntrypoint=_FakeEntrypoint,
    DurableObject=_FakeEntrypoint,
    Response=_FakeResponse,
    fetch=None,
)

sys.path.insert(0, "src")
entry = importlib.import_module("entry")


class _Env:
    GEMINI_API_KEY = "test-key"
    GEMINI_PROJECT_ID = "test-project"
    GEMINI_MODEL = "gemini-test"
    TRY_PROVIDER_TOKEN = "test-token"
    REPAIR_CHECKPOINTS = object()




class HealthCheckTests(unittest.TestCase):
    class Request:
        method = "GET"
        url = "https://worker.example/healthz"
        headers = {}

    def test_health_not_ready_without_provider_token(self):
        env = _Env()
        env.TRY_PROVIDER_TOKEN = ""
        instance = entry.Default()
        instance.env = env
        result = asyncio.run(instance.fetch(self.Request()))
        self.assertEqual(result["status"], "NOT_READY")
        self.assertFalse(result["provider_token_configured"])

    def test_health_not_ready_without_checkpoint_binding(self):
        env = _Env()
        env.REPAIR_CHECKPOINTS = None
        instance = entry.Default()
        instance.env = env
        result = asyncio.run(instance.fetch(self.Request()))
        self.assertEqual(result["status"], "NOT_READY")
        self.assertFalse(result["checkpoint_store_bound"])

    def test_health_not_ready_for_whitespace_provider_configuration(self):
        env = _Env()
        env.GEMINI_API_KEY = "   "
        instance = entry.Default()
        instance.env = env
        result = asyncio.run(instance.fetch(self.Request()))
        self.assertEqual(result["status"], "NOT_READY")

    def test_health_ready_only_when_required_bindings_exist(self):
        env = _Env()
        instance = entry.Default()
        instance.env = env
        result = asyncio.run(instance.fetch(self.Request()))
        self.assertEqual(result["status"], "READY")
        self.assertTrue(result["provider_token_configured"])
        self.assertTrue(result["checkpoint_store_bound"])


class BoundedBodyTests(unittest.TestCase):
    class Request:
        def __init__(self, body, content_length=None, chunk_size=65536):
            encoded = body.encode("utf-8") if isinstance(body, str) else bytes(body)
            self.headers = {}
            if content_length is not None:
                self.headers["Content-Length"] = str(content_length)
            chunks = [encoded[i:i + chunk_size] for i in range(0, len(encoded), chunk_size)]
            self.body = _FakeStream(chunks)

    def read(self, body, content_length=None, chunk_size=65536):
        request = self.Request(body, content_length, chunk_size)
        return asyncio.run(entry._read_bounded_json(request))

    def test_content_length_is_optional_for_streamed_body(self):
        self.assertEqual(self.read('{"ok":true}'), {"ok": True})

    def test_declared_oversize_is_rejected_before_stream_read(self):
        request = self.Request("{}", entry.MAX_BODY + 1)
        with self.assertRaisesRegex(ValueError, "body_too_large"):
            asyncio.run(entry._read_bounded_json(request))
        self.assertEqual(request.body.reader.read_count, 0)

    def test_exact_max_body_size_is_accepted(self):
        prefix = b'{"padding":"'
        suffix = b'"}'
        body = prefix + (b"x" * (entry.MAX_BODY - len(prefix) - len(suffix))) + suffix
        self.assertEqual(len(body), entry.MAX_BODY)
        payload = asyncio.run(entry._read_bounded_json(self.Request(body, entry.MAX_BODY)))
        self.assertEqual(len(payload["padding"]), entry.MAX_BODY - len(prefix) - len(suffix))
    def test_actual_stream_size_is_enforced_without_content_length(self):
        stream = _FakeStream([b"a" * 600000, b"b" * 400001, b"not-read"])
        request = type("Request", (), {"headers": {}, "body": stream})()
        with self.assertRaisesRegex(ValueError, "body_too_large"):
            asyncio.run(entry._read_bounded_json(request))
        self.assertTrue(stream.reader.cancelled)
        self.assertEqual(stream.reader.read_count, 2)
        self.assertTrue(stream.reader.released)

    def test_declared_and_actual_lengths_must_match(self):
        with self.assertRaisesRegex(ValueError, "body_size_mismatch"):
            self.read('{"x":1}', 2)

    def test_utf8_byte_length_is_used_across_chunks(self):
        body = json.dumps({"value": "á"})
        payload = self.read(body, len(body.encode("utf-8")), chunk_size=2)
        self.assertEqual(payload["value"], "á")

    def test_malformed_json_is_redacted(self):
        with self.assertRaisesRegex(ValueError, "invalid_json"):
            self.read("{broken}")

    def test_bounded_body_requires_object(self):
        with self.assertRaisesRegex(ValueError, "request_not_object"):
            self.read(json.dumps(["not", "object"]))

    def test_invalid_content_length_is_rejected_before_read(self):
        request = self.Request("{}", "1.5")
        with self.assertRaisesRegex(ValueError, "content_length_invalid"):
            asyncio.run(entry._read_bounded_json(request))
        self.assertEqual(request.body.reader.read_count, 0)

class WorkerValidationTests(unittest.TestCase):
    def assertRejects(self, path, content="x"):
        with self.assertRaises(ValueError):
            entry._validate({
                "schema": 2,
                "files": [{"path": path, "content": content}],
            })

    def test_rejects_protected_paths(self):
        for path in (
            ".aios/policy.py",
            ".github/workflows/x.yml",
            ".github/evil.yml",
            ".git/config",
            "secrets/key.txt",
            "tests/test_x.py",
            ".env",
            "credentials.json",
            "../escape.py",
            "pkg/../../escape.py",
            "/absolute.py",
            r"..\escape.py",
        ):
            self.assertRejects(path)

    def test_rejects_protected_source_snapshot(self):
        with self.assertRaisesRegex(ValueError, "protected_source_path"):
            entry._normalize_source_snapshot({".env": "secret"})
        with self.assertRaisesRegex(ValueError, "protected_source_path"):
            entry._normalize_source_snapshot({".aios/policy.py": "policy"})
        with self.assertRaisesRegex(ValueError, "protected_source_path"):
            entry._normalize_source_snapshot({".git/config": "metadata"})

    def test_source_snapshot_is_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate_source_path"):
            entry._normalize_source_snapshot({
                "src\\repair.py": "a",
                "src/repair.py": "b",
            })
        with self.assertRaisesRegex(ValueError, "source_file_too_large"):
            entry._normalize_source_snapshot({
                "src/large.py": "x" * (entry.MAX_FILE_BYTES + 1),
            })
        for path in (
            "vendor/.git/config",
            "pkg/.aios/policy.py",
            "pkg/.github/workflows/x.yml",
            "pkg/secrets/key.txt",
            "pkg/tests/test_x.py",
        ):
            with self.assertRaisesRegex(ValueError, "protected_source_path"):
                entry._normalize_source_snapshot({path: "x"})
        for path in (
            "vendor/.git/config",
            "pkg/.aios/policy.py",
            "pkg/.github/workflows/x.yml",
            "pkg/secrets/key.txt",
            "pkg/tests/test_x.py",
        ):
            with self.assertRaisesRegex(ValueError, "protected_source_path"):
                entry._normalize_source_snapshot({path: "x"})

    def test_request_identity_is_fail_closed(self):
        base = {
            "request_id": "req-1",
            "repository": "yanhul/try",
            "sha": "0" * 40,
            "attempt": 1,
            "failure": {"kind": "SyntaxError"},
            "source_snapshot": {"src/repair.py": "broken"},
        }
        for key, value in (
            ("request_id", ""),
            ("repository", ""),
            ("sha", "bad"),
            ("attempt", 0),
            ("attempt", True),
            ("request_id", "   "),
            ("repository", "   "),
        ):
            case = dict(base)
            case[key] = value
            with self.assertRaises(ValueError):
                asyncio.run(entry._propose(case, _Env()))

    def test_rejects_oversized_patch(self):
        self.assertRejects("src/large.py", "x" * (entry.MAX_FILE_BYTES + 1))

    def test_rejects_ambiguous_paths(self):
        for path in ("", "src/with\x00nul.py"):
            self.assertRejects(path)
        for path in (
            "vendor/.git/config",
            "pkg/.aios/policy.py",
            "pkg/.github/workflows/x.yml",
            "pkg/secrets/key.txt",
            "pkg/tests/test_x.py",
        ):
            self.assertRejects(path)
        for path in (
            "vendor/.git/config",
            "pkg/.aios/policy.py",
            "pkg/.github/workflows/x.yml",
            "pkg/secrets/key.txt",
            "pkg/tests/test_x.py",
        ):
            self.assertRejects(path)
        with self.assertRaisesRegex(ValueError, "duplicate_patch_path"):
            entry._validate({
                "schema": 2,
                "files": [
                    {"path": "src/repair.py", "content": "a"},
                    {"path": r"src\repair.py", "content": "b"},
                ],
            })

    def test_accepts_normal_source_patch(self):
        payload = entry._validate({
            "schema": 2,
            "root_cause": "syntax error",
            "proposed_fix": "repair function",
            "files": [{"path": r"src\repair.py", "content": "def repair():\n    return 1\n"}],
        })
        self.assertEqual(payload["files"][0]["path"], "src/repair.py")


class GeminiProtocolTests(unittest.TestCase):
    def test_malformed_success_response_is_protocol_failure(self):
        async def fake_fetch(*args, **kwargs):
            return _Response(200, payload={"unexpected": "shape"})

        original = entry.fetch
        entry.fetch = fake_fetch
        try:
            with self.assertRaisesRegex(RuntimeError, "gemini_protocol_error"):
                asyncio.run(entry._call_gemini("prompt", _Env()))
        finally:
            entry.fetch = original

    def test_non_object_model_json_is_protocol_failure(self):
        async def fake_fetch(*args, **kwargs):
            return _Response(
                200,
                payload={
                    "choices": [{
                        "message": {
                            "content": json.dumps(["not", "object"])
                        }
                    }]
                },
            )

        original = entry.fetch
        entry.fetch = fake_fetch
        try:
            with self.assertRaisesRegex(RuntimeError, "gemini_protocol_error"):
                asyncio.run(entry._call_gemini("prompt", _Env()))
        finally:
            entry.fetch = original


class GeminiProtocolTests(unittest.TestCase):
    def test_malformed_success_response_is_protocol_failure(self):
        async def fake_fetch(*args, **kwargs):
            return _Response(200, payload={"unexpected": "shape"})

        original = entry.fetch
        entry.fetch = fake_fetch
        try:
            with self.assertRaisesRegex(RuntimeError, "gemini_protocol_error"):
                asyncio.run(entry._call_gemini("prompt", _Env()))
        finally:
            entry.fetch = original

    def test_non_object_model_json_is_protocol_failure(self):
        async def fake_fetch(*args, **kwargs):
            return _Response(
                200,
                payload={
                    "choices": [{
                        "message": {
                            "content": json.dumps(["not", "object"])
                        }
                    }]
                },
            )

        original = entry.fetch
        entry.fetch = fake_fetch
        try:
            with self.assertRaisesRegex(RuntimeError, "gemini_protocol_error"):
                asyncio.run(entry._call_gemini("prompt", _Env()))
        finally:
            entry.fetch = original


class GeminiRetryTests(unittest.TestCase):
    def test_429_is_not_retried(self):
        calls = []

        async def fake_fetch(*args, **kwargs):
            calls.append(1)
            return _Response(429, detail="quota")

        original = entry.fetch
        entry.fetch = fake_fetch
        try:
            with self.assertRaisesRegex(RuntimeError, "gemini_quota_exhausted:429"):
                asyncio.run(entry._call_gemini("prompt", _Env()))
        finally:
            entry.fetch = original

        self.assertEqual(len(calls), 1)

    def test_nonretryable_400_is_terminal_without_retry(self):
        calls = []
        async def fake_fetch(*args, **kwargs):
            calls.append(1)
            return _Response(400, detail="bad request")
        original = entry.fetch
        entry.fetch = fake_fetch
        try:
            with self.assertRaisesRegex(RuntimeError, "gemini_http_400"):
                asyncio.run(entry._call_gemini("prompt", _Env()))
        finally:
            entry.fetch = original
        self.assertEqual(len(calls), 1)
    def test_transient_503_retries_then_succeeds(self):
        calls = []

        async def fake_fetch(*args, **kwargs):
            calls.append(1)
            if len(calls) < 3:
                return _Response(503, detail="temporary")
            return _Response(
                200,
                payload={
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "schema": 2,
                                "files": [{"path": "src/repair.py", "content": "x"}],
                            })
                        }
                    }]
                },
            )

        original = entry.fetch
        original_sleep = entry.asyncio.sleep
        entry.fetch = fake_fetch
        async def no_sleep(_):
            return None
        entry.asyncio.sleep = no_sleep
        try:
            payload = asyncio.run(entry._call_gemini("prompt", _Env()))
        finally:
            entry.fetch = original
            entry.asyncio.sleep = original_sleep

        self.assertEqual(len(calls), 3)
        self.assertEqual(payload["schema"], 2)


if __name__ == "__main__":
    unittest.main()


class _FakeStorage:
    def __init__(self):
        self.data = {}
    async def get(self, key):
        return self.data.get(key)
    async def put(self, key, value):
        self.data[key] = value


class _FakeContext:
    def __init__(self):
        self.storage = _FakeStorage()


class DurableCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.ctx = _FakeContext()
        self.checkpoint = entry.RepairCheckpoint(self.ctx, _Env())
        self.base = {
            "request_id": "req-1", "repository": "yanhul/try", "sha": "a" * 40,
            "attempt": 1, "phase": "OBSERVE", "state": "WORKING",
        }

    def write(self, **changes):
        payload = dict(self.base)
        payload.update(changes)
        return asyncio.run(self.checkpoint.write_checkpoint(payload))

    def test_checkpoint_is_persisted_and_identity_bound(self):
        first = self.write()
        self.assertTrue(first["persisted"])
        replay = self.write()
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["version"], 1)
        changed_same_phase = self.write(evidence_digest="d" * 64)
        self.assertEqual(changed_same_phase["error"], "checkpoint_replay_conflict")
        self.assertEqual(asyncio.run(self.checkpoint.read_checkpoint())["version"], 1)
        conflict = self.write(sha="b" * 40, phase="DECIDE")
        self.assertEqual(conflict["error"], "checkpoint_identity_conflict")

    def test_invalid_phase_skip_fails_closed(self):
        result = self.write(phase="PROPOSE")
        self.assertEqual(result["_http_status"], 409)
        self.assertEqual(result["error"], "initial_checkpoint_must_start_at_observe_attempt_1")

    def test_done_requires_persisted_evidence_digest(self):
        self.assertTrue(self.write()["persisted"])
        self.assertTrue(self.write(phase="DECIDE")["persisted"])
        self.assertTrue(self.write(phase="PROPOSE")["persisted"])
        self.assertTrue(self.write(phase="VERIFY")["persisted"])
        self.assertTrue(self.write(phase="PERSIST")["persisted"])
        denied = self.write(phase="PERSIST", state="DONE")
        self.assertEqual(denied["error"], "done_requires_persisted_evidence_digest")
        done = self.write(phase="PERSIST", state="DONE", evidence_digest="c" * 64)
        self.assertTrue(done["persisted"])
        terminal = self.write(state="BLOCKED", reason="late mutation")
        self.assertEqual(terminal["error"], "checkpoint_terminal")

    def test_retry_requires_blocked_then_resume(self):
        self.assertTrue(self.write()["persisted"])
        blocked = self.write(phase="OBSERVE", state="BLOCKED", reason="test failed")
        self.assertTrue(blocked["persisted"])
        resumed = self.write(attempt=2, phase="RESUME", state="WORKING")
        self.assertTrue(resumed["persisted"])
        self.assertEqual(resumed["version"], 3)


class EndpointAdmissionTests(unittest.TestCase):
    class Request:
        method = "POST"
        def __init__(self, path, body="{}", content_length=None, chunk_size=65536, method="POST"):
            self.method = method
            self.url = "https://worker.example" + path
            self.headers = {"Authorization": "Bearer test-token"}
            if content_length is not None:
                self.headers["Content-Length"] = str(content_length)
            encoded = body.encode("utf-8")
            chunks = [encoded[i:i + chunk_size] for i in range(0, len(encoded), chunk_size)]
            self.body = _FakeStream(chunks)

    class Namespace:
        def __init__(self):
            self.lookup_count = 0
            self.write_count = 0
        def idFromName(self, request_id):
            self.lookup_count += 1
            return request_id
        def get(self, object_id):
            namespace = self
            class Stub:
                async def write_checkpoint(self, body):
                    namespace.write_count += 1
                    return {"_http_status": 200, "persisted": True}
            return Stub()

    def setUp(self):
        self.env = _Env()
        self.worker = entry.Default()
        self.worker.env = self.env

    def test_propose_chunked_body_without_content_length_reaches_provider(self):
        request = self.Request("/v1/repair/propose", '{"request_id":"req-1"}')
        calls = []
        original = entry._propose
        async def fake_propose(*args):
            calls.append(1)
            return {"schema": 2}
        entry._propose = fake_propose
        try:
            result = asyncio.run(self.worker.fetch(request))
        finally:
            entry._propose = original
        self.assertEqual(result["schema"], 2)
        self.assertEqual(calls, [1])

    def test_propose_oversized_chunked_body_stops_before_provider(self):
        request = self.Request("/v1/repair/propose", "x" * (entry.MAX_BODY + 1))
        calls = []
        original = entry._propose
        async def fake_propose(*args):
            calls.append(1)
            return {"schema": 2}
        entry._propose = fake_propose
        try:
            result = asyncio.run(self.worker.fetch(request))
        finally:
            entry._propose = original
        self.assertEqual(result["error"], "body_too_large")
        self.assertEqual(calls, [])
        self.assertTrue(request.body.reader.cancelled)

    def test_checkpoint_chunked_body_without_content_length_persists(self):
        namespace = self.Namespace()
        self.env.REPAIR_CHECKPOINTS = namespace
        request = self.Request("/v1/repair/checkpoint", '{"request_id":"req-1"}')
        result = asyncio.run(self.worker.fetch(request))
        self.assertTrue(result["persisted"])
        self.assertEqual(namespace.lookup_count, 1)
        self.assertEqual(namespace.write_count, 1)

    def test_checkpoint_oversized_chunked_body_stops_before_storage(self):
        namespace = self.Namespace()
        self.env.REPAIR_CHECKPOINTS = namespace
        request = self.Request("/v1/repair/checkpoint", "x" * (entry.MAX_BODY + 1))
        result = asyncio.run(self.worker.fetch(request))
        self.assertEqual(result["error"], "body_too_large")
        self.assertEqual(namespace.lookup_count, 0)
        self.assertEqual(namespace.write_count, 0)
        self.assertTrue(request.body.reader.cancelled)



    def test_checkpoint_invalid_request_id_rejected_before_namespace_lookup(self):
        namespace = self.Namespace()
        self.env.REPAIR_CHECKPOINTS = namespace
        body = json.dumps({"request_id": "x" * 161})
        request = self.Request("/v1/repair/checkpoint", body)
        result = asyncio.run(self.worker.fetch(request))
        self.assertEqual(result["error"], "request_id_invalid")
        self.assertEqual(namespace.lookup_count, 0)
        self.assertEqual(namespace.write_count, 0)

    def test_checkpoint_get_invalid_request_id_rejected_before_namespace_lookup(self):
        namespace = self.Namespace()
        self.env.REPAIR_CHECKPOINTS = namespace
        request = self.Request(
            "/v1/repair/checkpoint/" + ("x" * 161),
            method="GET",
        )
        result = asyncio.run(self.worker.fetch(request))
        self.assertEqual(result["error"], "request_id_invalid")
        self.assertEqual(namespace.lookup_count, 0)

class ProviderFailureMappingTests(unittest.TestCase):
    class StatusResponse:
        @staticmethod
        def json(payload, status=200, headers=None):
            return {"_status": status, **payload}

    def _fetch(self, error):
        worker = entry.Default()
        worker.env = _Env()
        request = EndpointAdmissionTests.Request(
            "/v1/repair/propose", '{"request_id":"req-1"}'
        )
        original_response = entry.Response
        original_propose = entry._propose
        async def fail(*args):
            raise error
        entry.Response = self.StatusResponse
        entry._propose = fail
        try:
            return asyncio.run(worker.fetch(request))
        finally:
            entry.Response = original_response
            entry._propose = original_propose

    def test_nonretryable_gemini_400_is_upstream_failure_not_hold(self):
        result = self._fetch(RuntimeError("gemini_http_400"))
        self.assertEqual(result["_status"], 502)
        self.assertEqual(result["status"], "PROVIDER_UPSTREAM_REJECTED")
        self.assertEqual(result["reason"], "gemini_http_400")

    def test_unexpected_runtime_error_is_internal_error_not_hold(self):
        result = self._fetch(RuntimeError("internal details must not escape"))
        self.assertEqual(result["_status"], 500)
        self.assertEqual(result["status"], "PROVIDER_INTERNAL_ERROR")
        self.assertEqual(result["reason"], "RuntimeError")
class ProviderReadinessErrorMappingTests(unittest.TestCase):
    def test_missing_model_maps_to_provider_not_ready_503(self):
        class StatusResponse:
            @staticmethod
            def json(payload, status=200, headers=None):
                return {"_status": status, **payload}
        worker = entry.Default()
        worker.env = _Env()
        request = EndpointAdmissionTests.Request(
            "/v1/repair/propose", '{"request_id":"req-1"}'
        )
        original_response = entry.Response
        original_propose = entry._propose
        async def fail_model(*args):
            raise RuntimeError("provider_model_not_configured:GEMINI")
        entry.Response = StatusResponse
        entry._propose = fail_model
        try:
            result = asyncio.run(worker.fetch(request))
        finally:
            entry.Response = original_response
            entry._propose = original_propose
        self.assertEqual(result["_status"], 503)
        self.assertEqual(result["status"], "PROVIDER_NOT_READY")
        self.assertEqual(result["reason"], "provider_model_not_configured")
