import base64
import hashlib
import json

import pytest

from research import repair_external_integrations as ext


def _record(value):
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _envelope(run_id="123", repository="yanhul/try", base_sha="a" * 40):
    records = {
        "contracts": _record({"task_id": "try-ci-repair-" + run_id}),
        "permits": _record({"permit": "bounded"}),
        "attestations": _record({"signature": "issuer-signed"}),
    }
    return {
        "schema": 1,
        "run_id": run_id,
        "repository": repository,
        "base_sha": base_sha,
        "contract_id": "contract-123",
        "permit_id": "permit-123",
        "records": {
            kind: {
                "content_b64": base64.b64encode(raw).decode("ascii"),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            for kind, raw in records.items()
        },
    }


def test_fetch_authority_snapshot_writes_expected_records(monkeypatch, tmp_path):
    monkeypatch.setenv("AIOS_REPAIR_ISSUER_URL", "https://issuer.example")
    monkeypatch.setenv("AIOS_REPAIR_ISSUER_READ_TOKEN", "test-token")
    monkeypatch.setattr(ext, "_request_json", lambda *a, **k: _envelope())
    digests = ext.fetch_authority_snapshot(
        run_id="123", repository="yanhul/try", base_sha="a" * 40,
        destination=tmp_path / "snapshot",
    )
    root = tmp_path / "snapshot" / "authority"
    assert (root / "contracts" / "contract-123.json").is_file()
    assert (root / "permits" / "permit-123.json").is_file()
    assert (root / "attestations" / "permit-123.json").is_file()
    assert digests["contract_id"] == "contract-123"
    assert digests["permit_id"] == "permit-123"
    assert all(digests[kind + "_sha256"] for kind in ("contracts", "permits", "attestations"))


@pytest.mark.parametrize("field,value", [
    ("run_id", "999"),
    ("repository", "other/repo"),
    ("base_sha", "b" * 40),
])
def test_fetch_authority_snapshot_rejects_wrong_run_binding(monkeypatch, tmp_path, field, value):
    monkeypatch.setenv("AIOS_REPAIR_ISSUER_URL", "https://issuer.example")
    monkeypatch.setenv("AIOS_REPAIR_ISSUER_READ_TOKEN", "test-token")
    envelope = _envelope()
    envelope[field] = value
    monkeypatch.setattr(ext, "_request_json", lambda *a, **k: envelope)
    with pytest.raises(ext.ExternalIntegrationError, match="authority_envelope_identity_mismatch"):
        ext.fetch_authority_snapshot(
            run_id="123", repository="yanhul/try", base_sha="a" * 40,
            destination=tmp_path / "snapshot",
        )


def test_fetch_authority_snapshot_rejects_record_digest_tampering(monkeypatch, tmp_path):
    monkeypatch.setenv("AIOS_REPAIR_ISSUER_URL", "https://issuer.example")
    monkeypatch.setenv("AIOS_REPAIR_ISSUER_READ_TOKEN", "test-token")
    envelope = _envelope()
    envelope["records"]["permits"]["sha256"] = "0" * 64
    monkeypatch.setattr(ext, "_request_json", lambda *a, **k: envelope)
    with pytest.raises(ext.ExternalIntegrationError, match="authority_record_digest_mismatch:permits"):
        ext.fetch_authority_snapshot(
            run_id="123", repository="yanhul/try", base_sha="a" * 40,
            destination=tmp_path / "snapshot",
        )


def test_fetch_authority_snapshot_rejects_http_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("AIOS_REPAIR_ISSUER_URL", "http://issuer.example")
    monkeypatch.setenv("AIOS_REPAIR_ISSUER_READ_TOKEN", "test-token")
    with pytest.raises(ext.ExternalIntegrationError, match="must_be_https"):
        ext.fetch_authority_snapshot(
            run_id="123", repository="yanhul/try", base_sha="a" * 40,
            destination=tmp_path / "snapshot",
        )


def test_commit_candidate_requires_pass_and_verified_authority(monkeypatch, tmp_path):
    monkeypatch.setenv("AIOS_COMMIT_ADAPTER_URL", "https://commit.example")
    monkeypatch.setenv("AIOS_COMMIT_ADAPTER_TOKEN", "test-token")
    patch = tmp_path / "candidate.patch"
    patch.write_bytes(b"diff --git a/a.py b/a.py\n")
    result = tmp_path / "repair-result.json"
    result.write_text(json.dumps({"status": "BLOCKED"}), encoding="utf-8")
    receipt = tmp_path / "authority-receipt.json"
    receipt.write_text(json.dumps({
        "verified": True, "run_id": "123", "contract_id": "contract-123",
        "permit_id": "permit-123",
    }), encoding="utf-8")
    with pytest.raises(ext.ExternalIntegrationError, match="commit_candidate_repair_not_pass"):
        ext.submit_commit_candidate(
            run_id="123", repository="yanhul/try", base_sha="a" * 40,
            contract_id="contract-123", permit_id="permit-123",
            patch_path=patch, repair_result_path=result, authority_receipt_path=receipt,
        )


def test_commit_candidate_requires_adapter_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("AIOS_COMMIT_ADAPTER_URL", "https://commit.example")
    monkeypatch.setenv("AIOS_COMMIT_ADAPTER_TOKEN", "test-token")
    patch = tmp_path / "candidate.patch"
    patch.write_bytes(b"candidate patch")
    result = tmp_path / "repair-result.json"
    result.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    receipt = tmp_path / "authority-receipt.json"
    receipt.write_text(json.dumps({
        "verified": True, "run_id": "123", "contract_id": "contract-123",
        "permit_id": "permit-123",
    }), encoding="utf-8")
    monkeypatch.setattr(ext, "_request_json", lambda *a, **k: {"status": "UNKNOWN"})
    with pytest.raises(ext.ExternalIntegrationError, match="did_not_confirm_creation"):
        ext.submit_commit_candidate(
            run_id="123", repository="yanhul/try", base_sha="a" * 40,
            contract_id="contract-123", permit_id="permit-123",
            patch_path=patch, repair_result_path=result, authority_receipt_path=receipt,
        )



def test_fetch_authority_snapshot_rejects_symlinked_authority_root(monkeypatch, tmp_path):
    monkeypatch.setenv("AIOS_REPAIR_ISSUER_URL", "https://issuer.example")
    monkeypatch.setenv("AIOS_REPAIR_ISSUER_READ_TOKEN", "test-token")
    monkeypatch.setattr(ext, "_request_json", lambda *a, **k: _envelope())
    destination = tmp_path / "snapshot"
    destination.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (destination / "authority").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ext.ExternalIntegrationError, match="authority_destination_path_escape"):
        ext.fetch_authority_snapshot(
            run_id="123", repository="yanhul/try", base_sha="a" * 40,
            destination=destination,
        )
