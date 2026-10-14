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


def test_authority_gate_loads_and_verifies_persisted_attestation():
    source = Path("research/autonomous_repair.py").read_text(encoding="utf-8")
    gate = source.split("def authority(root, run_id):", 1)[1].split(
        "\ndef resolve_terminal_evidence", 1
    )[0]

    assert 'os.environ.get("AIOS_REPAIR_ATTESTATION_SECRET", "")' in gate
    assert "load_permit(str(durable_root), permit_id)" in gate
    assert "load_attestation(str(durable_root), permit_id)" in gate
    assert "verify_attestation(contract, permit, attestation, attestation_secret)" in gate
    assert "persist_attestation" not in gate
