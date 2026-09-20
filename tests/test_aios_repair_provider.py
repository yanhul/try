import json

import pytest

from research.aios_repair_provider import _validate, propose


def test_validate_rejects_control_plane_and_workflow_paths():
    base = {"schema": 2, "root_cause": "x", "proposed_fix": "y"}
    for path in [".aios/x.py", ".github/workflows/ci.yml", "tests/test_x.py", ".env"]:
        with pytest.raises(ValueError):
            _validate({**base, "files": [{"path": path, "content": "x"}]})


def test_validate_accepts_source_patch():
    out = _validate({
        "schema": 2,
        "root_cause": "syntax error",
        "proposed_fix": "fix syntax",
        "files": [{"path": "core/example.py", "content": "x = 1\n"}],
    })
    assert out["schema"] == 2
    assert out["files"][0]["path"] == "core/example.py"


def test_propose_passes_only_bounded_evidence(monkeypatch):
    seen = {}
    def fake_call(prompt):
        seen["prompt"] = json.loads(prompt)
        return {"schema": 2, "root_cause": "r", "proposed_fix": "f",
                "files": [{"path": "core/x.py", "content": "x=1\n"}]}
    monkeypatch.setattr("research.aios_repair_provider._call", fake_call)
    out = propose({
        "request_id": "r1",
        "repository": "yanhul/AIOS",
        "sha": "a" * 40,
        "attempt": 1,
        "failure": {"ci_failure_log_tail": "z" * 100000},
        "source_snapshot": {"core/x.py": "a" * 200000},
    })
    assert len(seen["failure"]["ci_failure_log_tail"]) == 80000
    assert len(seen["source_snapshot"]["core/x.py"]) == 120000
    assert out["schema"] == 2


def test_health_requires_provider_config(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    from research.aios_repair_provider import health
    assert health() == {"status": "READY", "provider": "gemini", "model": "test-model"}
