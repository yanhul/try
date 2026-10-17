from pathlib import Path
import hashlib
import json
import os
import sys
import types

import pytest

import research.autonomous_repair as runner
from research.verify_repair_authority import verify_and_write_receipt


def test_issuer_hmac_secret_never_enters_try_processes():
    verifier = Path("research/verify_repair_authority.py").read_text(encoding="utf-8")
    controller = Path("research/autonomous_repair.py").read_text(encoding="utf-8")
    assert "AIOS_REPAIR_ATTESTATION_SECRET" not in verifier
    assert "verify_attestation" not in verifier
    assert "persist_attestation" not in verifier
    assert "AIOS_REPAIR_ATTESTATION_SECRET" not in controller
    assert "_verify_preflight_receipt(durable_root, contract_id, permit_id, run_id)" in controller


def test_missing_preflight_receipt_blocks_before_authority_resolution(monkeypatch):
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_DIR", "/var/lib/aios-authority")
    monkeypatch.setenv("AIOS_REPAIR_CONTRACT_ID", "CT-test-contract")
    monkeypatch.setenv("AIOS_REPAIR_PERMIT_ID", "PT-test-permit")
    monkeypatch.delenv("AIOS_REPAIR_AUTHORITY_GATE_RECEIPT", raising=False)
    monkeypatch.setattr(Path, "is_dir", lambda self: True)

    with pytest.raises(RuntimeError, match="authority_records_rejected") as exc:
        runner.authority(Path("."), 12345)
    assert "authority_preflight_receipt_missing" in str(exc.value)
    assert "AIOS_REPAIR_AUTHORITY_DIR" not in os.environ
    assert "AIOS_REPAIR_CONTRACT_ID" not in os.environ
    assert "AIOS_REPAIR_PERMIT_ID" not in os.environ


def test_preflight_receipt_binds_exact_persisted_record_bytes(tmp_path, monkeypatch):
    root = tmp_path / "aios"
    for kind, record_id, field in (
        ("contracts", "CT-test", "contract_sha256"),
        ("permits", "PT-test", "permit_sha256"),
        ("attestations", "PT-test", "attestation_sha256"),
    ):
        path = root / "authority" / kind / (record_id + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"record":"' + kind + '"}', encoding="utf-8")

    receipt = {
        "schema": 1, "verified": True, "run_id": "77", "authority_root": str(root.resolve()),
        "contract_id": "CT-test", "permit_id": "PT-test",
    }
    for kind, record_id, field in (
        ("contracts", "CT-test", "contract_sha256"),
        ("permits", "PT-test", "permit_sha256"),
        ("attestations", "PT-test", "attestation_sha256"),
    ):
        path = root / "authority" / kind / (record_id + ".json")
        receipt[field] = hashlib.sha256(path.read_bytes()).hexdigest()

    receipt_path = tmp_path / "authority-gate.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_GATE_RECEIPT", str(receipt_path))
    runner._verify_preflight_receipt(root.resolve(), "CT-test", "PT-test", 77)

    permit_path = root / "authority" / "permits" / "PT-test.json"
    permit_path.write_text('{"record":"tampered"}', encoding="utf-8")
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_GATE_RECEIPT", str(receipt_path))
    with pytest.raises(RuntimeError, match="authority_preflight_record_digest_mismatch:permits"):
        runner._verify_preflight_receipt(root.resolve(), "CT-test", "PT-test", 77)


def test_isolated_verifier_rejects_invalid_attestation_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_DIR", "/var/lib/aios-authority")
    monkeypatch.setenv("AIOS_REPAIR_CONTRACT_ID", "CT-test-contract")
    monkeypatch.setenv("AIOS_REPAIR_PERMIT_ID", "PT-test-permit")
    monkeypatch.setenv("AIOS_REPAIR_ATTESTATION_VERIFIED", "true")
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_STORE_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("AIOS_REPAIR_RUN_ID", "12345")
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_GATE_RECEIPT", str(tmp_path / "gate.json"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(Path, "is_dir", lambda self: True)

    contract = {
        "task_id": "try-ci-repair-12345", "actor": "try-autonomous-repair",
        "scope": "repository", "capabilities": ["repo_patch@1"],
        "allowed_effects": ["external_effect"], "max_attempts": 3,
    }
    authority_module = types.ModuleType("core.authority")
    authority_module.authorize = lambda *args: True
    authority_module.load_contract = lambda *args: contract
    authority_module.load_permit = lambda *args: {
        "contract_id": "CT-test-contract", "permit_id": "PT-test-permit", "issuer": "external"
    }
    authority_module.load_attestation = lambda *args: {"signature": "forged", "attestation_type": "INVALID"}
    monkeypatch.setitem(sys.modules, "core.authority", authority_module)

    with pytest.raises(RuntimeError, match="authority_attestation_identity_invalid"):
        verify_and_write_receipt()


def test_provider_token_is_only_temporarily_exposed_for_proposal_calls():
    source = Path("research/autonomous_repair.py").read_text(encoding="utf-8")
    assert 'provider_token = os.environ.pop("TRY_REPAIR_PROVIDER_TOKEN", "")' in source
    assert 'os.environ["TRY_REPAIR_PROVIDER_TOKEN"] = provider_token' in source
    assert 'os.environ.pop("TRY_REPAIR_PROVIDER_TOKEN", None)' in source
    assert source.rindex('os.environ.pop("TRY_REPAIR_PROVIDER_TOKEN", None)') < source.index("tested=worker.test()")


def test_isolated_verifier_writes_receipt_only_after_independent_hmac_proof(monkeypatch, tmp_path):
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_DIR", "/var/lib/aios-authority")
    monkeypatch.setenv("AIOS_REPAIR_CONTRACT_ID", "CT-test-contract")
    monkeypatch.setenv("AIOS_REPAIR_PERMIT_ID", "PT-test-permit")
    monkeypatch.setenv("AIOS_REPAIR_ATTESTATION_VERIFIED", "true")
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_STORE_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("AIOS_REPAIR_RUN_ID", "12345")
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_GATE_RECEIPT", str(tmp_path / "gate.json"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(Path, "is_dir", lambda self: True)
    monkeypatch.setattr(
        "research.verify_repair_authority._record_digest",
        lambda root, kind, record_id: kind + "-digest",
    )

    contract = {
        "task_id": "try-ci-repair-12345", "actor": "try-autonomous-repair",
        "scope": "repository", "capabilities": ["repo_patch@1"],
        "allowed_effects": ["external_effect"], "max_attempts": 3,
    }
    authority_module = types.ModuleType("core.authority")
    authority_module.authorize = lambda *args: True
    authority_module.load_contract = lambda *args: contract
    authority_module.load_permit = lambda *args: {
        "contract_id": "CT-test-contract", "permit_id": "PT-test-permit", "issuer": "external"
    }
    authority_module.load_attestation = lambda *args: {
        "signature": "validated-by-independent-verifier",
        "attestation_type": "EXECUTION_PERMIT_ATTESTATION",
        "algorithm": "HMAC-SHA256",
        "contract_id": "CT-test-contract",
        "permit_id": "PT-test-permit",
        "issuer": "yanhul/aios-authority-store",
    }
    monkeypatch.setitem(sys.modules, "core.authority", authority_module)

    receipt_path = verify_and_write_receipt()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["verified"] is True
    assert receipt["run_id"] == "12345"
    assert receipt["contract_id"] == "CT-test-contract"
    assert receipt["permit_id"] == "PT-test-permit"
    assert receipt["contract_sha256"] == "contracts-digest"
    assert receipt["permit_sha256"] == "permits-digest"
    assert receipt["attestation_sha256"] == "attestations-digest"
    assert receipt["attestation_verified_by"] == "independent-git-authority-verifier"
    assert receipt["authority_store_commit_sha"] == "a" * 40
