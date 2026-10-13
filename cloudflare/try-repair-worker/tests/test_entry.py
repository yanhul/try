import asyncio
import importlib
import json
import sys
import types
import unittest


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



class BoundedBodyTests(unittest.TestCase):
    class Request:
        def __init__(self, body):
            self.body = body
        async def text(self):
            return self.body

    def test_actual_body_size_is_enforced(self):
        request = self.Request("x" * (entry.MAX_BODY + 1))
        with self.assertRaisesRegex(ValueError, "body_too_large"):
            asyncio.run(entry._read_bounded_json(request))

    def test_bounded_body_requires_object(self):
        request = self.Request(json.dumps(["not", "object"]))
        with self.assertRaisesRegex(ValueError, "request_not_object"):
            asyncio.run(entry._read_bounded_json(request))

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
        denied = self.write(state="DONE")
        self.assertEqual(denied["error"], "done_requires_persisted_evidence_digest")
        done = self.write(state="DONE", evidence_digest="c" * 64)
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
