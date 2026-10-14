from pathlib import Path

import pytest

from research.autonomous_repair import authority


def test_missing_external_attestation_secret_blocks_before_authority_io(monkeypatch):
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_DIR", "/var/lib/aios")
    monkeypatch.setenv("AIOS_REPAIR_CONTRACT_ID", "contract-external")
    monkeypatch.setenv("AIOS_REPAIR_PERMIT_ID", "permit-external")
    monkeypatch.delenv("AIOS_REPAIR_ATTESTATION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="authority_attestation_missing"):
        authority(Path("."), 12345)


def test_attestation_secret_is_removed_before_any_child_process_can_inherit_it(monkeypatch):
    import os

    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_DIR", "/var/lib/aios")
    monkeypatch.setenv("AIOS_REPAIR_CONTRACT_ID", "contract-external")
    monkeypatch.setenv("AIOS_REPAIR_PERMIT_ID", "permit-external")
    monkeypatch.setenv("AIOS_REPAIR_ATTESTATION_SECRET", "must-not-leak-to-test-child")

    with pytest.raises(RuntimeError, match="authority_directory_missing"):
        authority(Path("."), 12345)
    assert "AIOS_REPAIR_ATTESTATION_SECRET" not in os.environ
    assert "AIOS_REPAIR_AUTHORITY_DIR" not in os.environ
    assert "AIOS_REPAIR_CONTRACT_ID" not in os.environ
    assert "AIOS_REPAIR_PERMIT_ID" not in os.environ


def test_authority_gate_loads_and_verifies_persisted_attestation():
    source = Path("research/autonomous_repair.py").read_text(encoding="utf-8")
    gate = source.split("def authority(root, run_id):", 1)[1].split(
        "\ndef resolve_terminal_evidence", 1
    )[0]

    assert 'os.environ.pop("AIOS_REPAIR_ATTESTATION_SECRET", "")' in gate
    assert "load_permit(str(durable_root), permit_id)" in gate
    assert "load_attestation(str(durable_root), permit_id)" in gate
    assert "verify_attestation(contract, permit, attestation, attestation_secret)" in gate
    assert "persist_attestation" not in gate


def test_provider_token_is_only_temporarily_exposed_for_proposal_calls():
    source = Path("research/autonomous_repair.py").read_text(encoding="utf-8")
    assert 'provider_token = os.environ.pop("TRY_REPAIR_PROVIDER_TOKEN", "")' in source
    assert 'os.environ["TRY_REPAIR_PROVIDER_TOKEN"] = provider_token' in source
    assert 'os.environ.pop("TRY_REPAIR_PROVIDER_TOKEN", None)' in source
    assert source.rindex('os.environ.pop("TRY_REPAIR_PROVIDER_TOKEN", None)') < source.index("tested=worker.test()")
