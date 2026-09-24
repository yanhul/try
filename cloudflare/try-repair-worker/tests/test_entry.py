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
    Response=_FakeResponse,
    fetch=None,
)

sys.path.insert(0, "src")
entry = importlib.import_module("entry")


class _Env:
    GEMINI_API_KEY = "test-key"
    GEMINI_PROJECT_ID = "test-project"
    GEMINI_MODEL = "gemini-test"


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
