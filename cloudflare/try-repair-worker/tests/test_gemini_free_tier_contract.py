"""Gemini Free Tier request-contract tests; no live credential or network use."""
import asyncio
import importlib
import json
import sys
import types
from pathlib import Path


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
    GEMINI_PROJECT_ID = "test-project"
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
                        "files": [{"path": "src/fix.py", "content": "fixed = True\n"}],
                    })
                }
            }]
        }

    async def text(self):
        return ""


def test_gemini_openai_compat_request_contract(monkeypatch):
    seen = {}

    async def fake_fetch(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return _Response()

    monkeypatch.setattr(entry, "fetch", fake_fetch)
    result = asyncio.run(entry._call_gemini("bounded prompt", _Env()))

    assert result["schema"] == 2
    assert seen["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    assert seen["method"] == "POST"
    assert seen["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer test-gemini-key",
    }
    body = json.loads(seen["body"])
    assert body["model"] == "gemini-test"
    assert body["temperature"] == 0
    assert body["max_tokens"] == 6000
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1] == {"role": "user", "content": "bounded prompt"}


def test_gemini_missing_key_or_project_fails_before_network(monkeypatch):
    calls = []

    async def fake_fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return _Response()

    monkeypatch.setattr(entry, "fetch", fake_fetch)
    for attribute, value in (
        ("GEMINI_API_KEY", ""),
        ("GEMINI_API_KEY", "   "),
        ("GEMINI_PROJECT_ID", ""),
        ("GEMINI_PROJECT_ID", "   "),
    ):
        env = _Env()
        setattr(env, attribute, value)
        try:
            asyncio.run(entry._call_gemini("prompt", env))
        except RuntimeError as exc:
            assert "provider_not_configured:GEMINI" in str(exc)
        else:
            raise AssertionError("missing Gemini configuration was accepted")
    assert calls == []


def test_gemini_blank_model_fails_closed_without_fallback(monkeypatch):
    calls = []

    async def fake_fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return _Response()

    monkeypatch.setattr(entry, "fetch", fake_fetch)
    env = _Env()
    env.GEMINI_MODEL = "   "
    try:
        asyncio.run(entry._call_gemini("prompt", env))
    except RuntimeError as exc:
        assert "provider_model_not_configured:GEMINI" in str(exc)
    else:
        raise AssertionError("blank model unexpectedly selected an implicit fallback")
    assert calls == []
