"""Gemini Free Tier request-contract tests; no live credential or network use."""
import asyncio
import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class _FakeEntrypoint:
    pass


class _FakeResponse:
    @staticmethod
    def json(payload, status=200, headers=None):
        return payload


sys.modules.setdefault(
    "workers",
    types.SimpleNamespace(
        WorkerEntrypoint=_FakeEntrypoint,
        DurableObject=_FakeEntrypoint,
        Response=_FakeResponse,
        fetch=None,
    ),
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
entry = importlib.import_module("entry")


class _Env:
    GEMINI_API_KEY = "  test-gemini-key  "
    GEMINI_MODEL = "gemini-test"


class _Response:
    status = 200
    ok = True

    async def json(self):
        return {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "schema": 2,
                        "root_cause": "fixture",
                        "proposed_fix": "repair",
                        "files": [{"path": "src/fix.py", "content": "fixed = True\\n"}],
                    })
                }
            }]
        }

    async def text(self):
        return ""


class GeminiFreeTierContractTests(unittest.TestCase):
    def test_gemini_openai_compat_request_contract(self):
        seen = {}

        async def fake_fetch(url, **kwargs):
            seen["url"] = url
            seen.update(kwargs)
            return _Response()

        with patch.object(entry, "fetch", fake_fetch):
            result = asyncio.run(entry._call_gemini("bounded prompt", _Env()))

        self.assertEqual(result["schema"], 2)
        self.assertEqual(
            seen["url"],
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        )
        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["headers"], {
            "Content-Type": "application/json",
            "Authorization": "Bearer test-gemini-key",
        })
        body = json.loads(seen["body"])
        self.assertEqual(body["model"], "gemini-test")
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["max_tokens"], 6000)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(body["messages"][1], {"role": "user", "content": "bounded prompt"})

    def test_gemini_missing_key_fails_before_network(self):
        calls = []

        async def fake_fetch(*args, **kwargs):
            calls.append((args, kwargs))
            return _Response()

        with patch.object(entry, "fetch", fake_fetch):
            for attribute, value in (
                ("GEMINI_API_KEY", ""),
                ("GEMINI_API_KEY", "   "),
            ):
                env = _Env()
                setattr(env, attribute, value)
                with self.subTest(attribute=attribute, value=repr(value)):
                    with self.assertRaisesRegex(RuntimeError, "provider_not_configured:GEMINI"):
                        asyncio.run(entry._call_gemini("prompt", env))
        self.assertEqual(calls, [])

    def test_gemini_blank_model_fails_closed_without_fallback(self):
        calls = []

        async def fake_fetch(*args, **kwargs):
            calls.append((args, kwargs))
            return _Response()

        env = _Env()
        env.GEMINI_MODEL = "   "
        with patch.object(entry, "fetch", fake_fetch):
            with self.assertRaisesRegex(RuntimeError, "provider_model_not_configured:GEMINI"):
                asyncio.run(entry._call_gemini("prompt", env))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
