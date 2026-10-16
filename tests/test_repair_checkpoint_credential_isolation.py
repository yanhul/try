"""Regression tests for credential isolation in the autonomous repair controller."""
import os


def test_checkpoint_token_is_scoped_to_checkpoint_http_call(monkeypatch):
    import research.autonomous_repair as controller

    observed = []
    monkeypatch.setattr(controller, "_CHECKPOINT_TOKEN", "checkpoint-secret")
    monkeypatch.delenv("TRY_REPAIR_CHECKPOINT_TOKEN", raising=False)

    def fake_get(*args, **kwargs):
        observed.append(os.environ.get("TRY_REPAIR_CHECKPOINT_TOKEN"))
        return {"request_id": "r"}

    monkeypatch.setattr(controller, "_get_checkpoint", fake_get)
    assert controller.get_checkpoint(request_id="r") == {"request_id": "r"}
    assert observed == ["checkpoint-secret"]
    assert "TRY_REPAIR_CHECKPOINT_TOKEN" not in os.environ


def test_checkpoint_write_token_is_scoped_to_checkpoint_http_call(monkeypatch):
    import research.autonomous_repair as controller

    observed = []
    monkeypatch.setattr(controller, "_CHECKPOINT_TOKEN", "checkpoint-secret")
    monkeypatch.delenv("TRY_REPAIR_CHECKPOINT_TOKEN", raising=False)

    def fake_persist(*args, **kwargs):
        observed.append(os.environ.get("TRY_REPAIR_CHECKPOINT_TOKEN"))
        return {"persisted": True}

    monkeypatch.setattr(controller, "_persist_checkpoint", fake_persist)
    assert controller.persist_checkpoint(request_id="r") == {"persisted": True}
    assert observed == ["checkpoint-secret"]
    assert "TRY_REPAIR_CHECKPOINT_TOKEN" not in os.environ


def test_checkpoint_and_proposal_credentials_are_distinct_in_workflow():
    from pathlib import Path

    workflow = Path(".github/workflows/try-autonomous-repair.yml").read_text()
    client = Path("research/repair_checkpoint.py").read_text()
    controller = Path("research/autonomous_repair.py").read_text()

    assert "TRY_REPAIR_CHECKPOINT_TOKEN: ${{ secrets.TRY_REPAIR_CHECKPOINT_TOKEN }}" in workflow
    assert 'os.environ.get("TRY_REPAIR_CHECKPOINT_TOKEN", "")' in client
    assert 'os.environ.pop("TRY_REPAIR_CHECKPOINT_TOKEN", "").strip()' in controller
    assert 'os.environ.pop("TRY_REPAIR_PROVIDER_TOKEN", "")' in controller
    assert 'os.environ.get("TRY_REPAIR_PROVIDER_TOKEN", "")' not in client


def test_uncertain_aios_apply_is_persisted_unknown_and_reconciliation_blocked(monkeypatch, tmp_path):
    import json
    from research import autonomous_repair as controller

    monkeypatch.chdir(tmp_path)
    persisted = []
    monkeypatch.setattr(controller, "persist_checkpoint", lambda **kwargs: persisted.append(kwargs))
    result = controller.record_unknown_apply_outcome(
        checkpoint_id="try-ci-repair:123",
        repository="yanhul/try",
        sha="a" * 40,
        attempt=2,
        phase="PROPOSE",
        reason="worker died after partial write",
    )

    on_disk = json.loads((tmp_path / "repair-result.json").read_text(encoding="utf-8"))
    assert result == on_disk
    assert result["status"] == "UNKNOWN"
    assert result["reconciliation_required"] is True
    assert "reconciliation_required" in result["reason"]
    assert persisted == [{
        "request_id": "try-ci-repair:123",
        "repository": "yanhul/try",
        "sha": "a" * 40,
        "attempt": 2,
        "phase": "PROPOSE",
        "state": "BLOCKED",
        "reason": result["reason"],
    }]
    with __import__("pytest").raises(controller.RepairCheckpointError, match="reconciliation_required"):
        controller.select_resume_attempt(
            {"repository": "yanhul/try", "sha": "a" * 40, "state": "BLOCKED",
             "attempt": 2, "reason": result["reason"]},
            repository="yanhul/try", sha="a" * 40,
        )


def test_uncertain_verification_exception_stops_retry_after_mutation():
    from pathlib import Path

    controller = Path("research/autonomous_repair.py").read_text()
    # A worker.test() exception occurs after apply_via_aios has returned; the
    # mutated tree must not receive another candidate until reconciliation.
    assert 'if current_phase in {"PROPOSE", "VERIFY"}:' in controller
    assert "independent reconciliation" in controller
