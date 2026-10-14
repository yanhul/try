"""Regression tests for the autonomous repair runner's AIOS authority gate.

These tests prove fail-closed behavior and that persisted authority resolution is
called before the runner is allowed to continue. The AIOS repository separately
owns integration tests for the authority store implementation.
"""
import sys
import types

import pytest

from research.autonomous_repair import authority


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
