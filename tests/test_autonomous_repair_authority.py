"""Regression tests for the autonomous repair runner's AIOS authority gate.

These tests prove fail-closed behavior and that persisted authority resolution is
called before the runner is allowed to continue. The AIOS repository separately
owns integration tests for the authority store implementation.
"""
import sys
import types

import pytest

from research.autonomous_repair import authority, resolve_terminal_evidence


def _set_authority_env(monkeypatch, directory="/var/lib/aios-authority"):
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_DIR", directory)
    monkeypatch.setenv("AIOS_REPAIR_CONTRACT_ID", "CT-test-contract")
    monkeypatch.setenv("AIOS_REPAIR_PERMIT_ID", "PT-test-permit")


def test_authority_missing_configuration_fails_closed(monkeypatch):
    for key in (
        "AIOS_REPAIR_AUTHORITY_DIR",
        "AIOS_REPAIR_CONTRACT_ID",
        "AIOS_REPAIR_PERMIT_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="authority_not_provisioned"):
        authority(None, 123)


def test_authority_rejects_missing_persistent_directory(monkeypatch):
    _set_authority_env(monkeypatch, "/var/lib/does-not-exist")
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: False)

    with pytest.raises(RuntimeError, match="authority_directory_missing"):
        authority(None, 123)


@pytest.mark.parametrize("directory", ["/tmp/aios-authority", "/var/tmp/aios-authority", "/opt/temporary/authority"])
def test_authority_rejects_temporary_directory(monkeypatch, directory):
    _set_authority_env(monkeypatch, directory)
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: True)

    with pytest.raises(RuntimeError, match="authority_directory_must_not_be_temporary"):
        authority(None, 123)


def test_authority_resolves_exact_contract_and_permit_before_return(monkeypatch):
    _set_authority_env(monkeypatch)
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: True)
    calls = []

    module = types.ModuleType("core.authority")
    module.authorize = lambda directory, contract_id, permit_id: calls.append(
        (directory, contract_id, permit_id)
    )
    module.load_contract = lambda directory, contract_id: {
        "task_id": "try-ci-repair-123",
        "actor": "try-autonomous-repair",
        "scope": "repository",
        "capabilities": ["repo_patch@1"],
        "allowed_effects": ["external_effect"],
        "max_attempts": 3,
    }
    monkeypatch.setitem(sys.modules, "core.authority", module)

    contract_id, permit_id, directory = authority(None, 123)

    assert (contract_id, permit_id) == ("CT-test-contract", "PT-test-permit")
    assert str(directory) == "/var/lib/aios-authority"
    assert calls == [("/var/lib/aios-authority", "CT-test-contract", "PT-test-permit")]


def test_rejected_persisted_authority_fails_closed(monkeypatch):
    _set_authority_env(monkeypatch)
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: True)

    module = types.ModuleType("core.authority")
    def reject(*args):
        raise ValueError("permit is not bound to this contract")
    module.authorize = reject
    module.load_contract = lambda *args: (_ for _ in ()).throw(AssertionError("must not load rejected contract"))
    monkeypatch.setitem(sys.modules, "core.authority", module)

    with pytest.raises(RuntimeError, match="authority_records_rejected"):
        authority(None, 123)

@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("task_id", "try-ci-repair-other-run", "contract_task_id_mismatch"),
        ("actor", "untrusted-actor", "contract_actor_mismatch"),
        ("scope", "global", "contract_scope_mismatch"),
        ("capabilities", [], "contract_patch_capability_missing"),
        ("allowed_effects", [], "contract_patch_effect_not_allowed"),
        ("max_attempts", 4, "contract_attempt_budget_exceeds_runner_limit"),
    ],
)
def test_authority_rejects_scope_or_identity_mismatch(monkeypatch, field, value, message):
    _set_authority_env(monkeypatch)
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: True)
    contract = {
        "task_id": "try-ci-repair-123",
        "actor": "try-autonomous-repair",
        "scope": "repository",
        "capabilities": ["repo_patch@1"],
        "allowed_effects": ["external_effect"],
        "max_attempts": 3,
    }
    contract[field] = value
    module = types.ModuleType("core.authority")
    module.authorize = lambda *args: True
    module.load_contract = lambda *args: contract
    monkeypatch.setitem(sys.modules, "core.authority", module)

    with pytest.raises(RuntimeError, match="authority_records_rejected") as exc:
        authority(None, 123)
    assert message in str(exc.value)

def test_main_blocks_before_proposal_when_authority_is_missing(monkeypatch, tmp_path):
    import json
    import research.autonomous_repair as runner

    monkeypatch.chdir(tmp_path)
    log = tmp_path / "ci.log"
    log.write_text("synthetic CI failure for authority-gate regression", encoding="utf-8")
    monkeypatch.setenv("AIOS_REPAIR_SHA", "a" * 40)
    monkeypatch.setenv("AIOS_REPAIR_RUN_ID", "123")
    monkeypatch.setenv("AIOS_REPAIR_LOG", str(log))
    monkeypatch.delenv("AIOS_REPAIR_EVIDENCE", raising=False)
    for key in (
        "AIOS_REPAIR_AUTHORITY_DIR",
        "AIOS_REPAIR_CONTRACT_ID",
        "AIOS_REPAIR_PERMIT_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(runner, "get_checkpoint", lambda **kwargs: None)
    checkpoint_writes = []
    monkeypatch.setattr(runner, "persist_checkpoint", lambda **kwargs: checkpoint_writes.append(kwargs))

    worker_module = types.ModuleType("core.agent_repair_worker")
    worker_module.AgentRepairWorker = type("AgentRepairWorker", (), {})
    worker_module.ProposedFile = type("ProposedFile", (), {})
    provider_module = types.ModuleType("core.try_repair_provider")
    proposals = []
    provider_module.propose = lambda **kwargs: proposals.append(kwargs)
    provider_module.TryRepairProviderError = type("TryRepairProviderError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "core.agent_repair_worker", worker_module)
    monkeypatch.setitem(sys.modules, "core.try_repair_provider", provider_module)

    assert runner.main() == 2
    result = json.loads((tmp_path / "repair-result.json").read_text(encoding="utf-8"))
    assert result["status"] == "BLOCKED"
    assert result["authority_required"] is True
    assert proposals == []
    assert checkpoint_writes[-1]["state"] == "BLOCKED"



def test_terminal_evidence_blocks_when_effect_receipt_is_not_persisted(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "core.evidence", types.SimpleNamespace(
        verify_evidence=lambda record: True
    ))
    reason = resolve_terminal_evidence(
        tmp_path, ["EV-test"], run_id=123, base_sha="a" * 40,
        applied={"effect_id": "EF-" + "b" * 64},
        contract_id="CT-test", permit_id="PT-test",
    )
    assert reason == "terminal_receipt_blocked:persisted_effect_unavailable:FileNotFoundError"


def test_terminal_evidence_requires_resolved_verified_run_and_sha_lineage(tmp_path, monkeypatch):
    import hashlib
    import json

    def evidence(evidence_id, level, source_ref, claim, run_id, provider, artifact_ref=None):
        record = {
            "evidence_id": evidence_id, "level": level, "source_ref": source_ref,
            "claim": claim, "run_id": str(run_id), "provider": provider,
            "artifact_ref": artifact_ref, "parent_evidence_id": None,
        }
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        record["digest"] = hashlib.sha256(canonical).hexdigest()
        return record

    def verify(record):
        candidate = dict(record)
        digest = candidate.pop("digest", None)
        canonical = json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        return digest == hashlib.sha256(canonical).hexdigest()

    monkeypatch.setitem(sys.modules, "core.evidence", types.SimpleNamespace(verify_evidence=verify))
    root = tmp_path
    (root / "effects").mkdir()
    (root / "evidence").mkdir()
    sha = "a" * 40
    effect_id = "EF-" + "b" * 64
    effect_evidence = evidence("EV-effect", "OBSERVED", "aios://effect", "patch application observed",
                               123, "aios-worker")
    effect = {
        "effect_id": effect_id, "state": "OBSERVED_SUCCESS",
        "contract_id": "CT-test", "permit_id": "PT-test",
        "actor": "try-autonomous-repair", "attempt_id": effect_id + ":attempt:1",
        "provider": "aios-worker",
        "provider_observation": {
            "attempt_id": effect_id + ":attempt:1", "provider": "aios-worker",
            "evidence": effect_evidence,
        },
    }
    (root / "effects" / (effect_id + ".json")).write_text(json.dumps(effect), encoding="utf-8")
    test_evidence = evidence(
        "EV-test", "VERIFIED_DIGITAL",
        f"github-actions://yanhul/try/commit/{sha}",
        "pytest test verification passed", 123, "github-actions",
        artifact_ref=f"artifact://runs/123/{sha}/pytest.xml",
    )
    (root / "evidence" / "EV-test.json").write_text(json.dumps(test_evidence), encoding="utf-8")

    assert resolve_terminal_evidence(
        root, ["EV-test"], run_id=123, base_sha=sha, applied={"effect_id": effect_id},
        contract_id="CT-test", permit_id="PT-test",
    ) is None

    test_evidence["run_id"] = "999"
    (root / "evidence" / "EV-test.json").write_text(json.dumps(test_evidence), encoding="utf-8")
    assert "run_identity_mismatch" in resolve_terminal_evidence(
        root, ["EV-test"], run_id=123, base_sha=sha, applied={"effect_id": effect_id},
        contract_id="CT-test", permit_id="PT-test",
    )
