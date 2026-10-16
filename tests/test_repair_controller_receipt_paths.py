"""Regression tests for controller-side authority receipt path containment."""
import json

import pytest

from research.autonomous_repair import _verify_preflight_receipt


def _receipt(monkeypatch, tmp_path, root):
    path = tmp_path / "authority-receipt.json"
    path.write_text(json.dumps({
        "schema": 1,
        "verified": True,
        "run_id": "123",
        "authority_root": str(root.resolve()),
        "contract_id": "contract-1",
        "permit_id": "permit-1",
        "contract_sha256": "0" * 64,
        "permit_sha256": "0" * 64,
        "attestation_sha256": "0" * 64,
    }), encoding="utf-8")
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_GATE_RECEIPT", str(path))


def test_controller_rejects_authority_root_symlink_escape(monkeypatch, tmp_path):
    root = tmp_path / "aios"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "authority").symlink_to(outside, target_is_directory=True)
    _receipt(monkeypatch, tmp_path, root)

    with pytest.raises(RuntimeError, match="authority_directory_path_escape"):
        _verify_preflight_receipt(root, "contract-1", "permit-1", 123)


def test_controller_rejects_record_directory_symlink_escape(monkeypatch, tmp_path):
    root = tmp_path / "aios"
    authority = root / "authority"
    authority.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (authority / "contracts").symlink_to(outside, target_is_directory=True)
    _receipt(monkeypatch, tmp_path, root)

    with pytest.raises(RuntimeError, match="authority_record_directory_escape"):
        _verify_preflight_receipt(root, "contract-1", "permit-1", 123)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", True),
        ("schema", "1"),
        ("run_id", 123),
        ("authority_root", 17),
        ("contract_id", ["contract-1"]),
        ("permit_id", None),
    ],
)
def test_controller_rejects_receipt_identity_runtime_type_confusion(
    monkeypatch, tmp_path, field, value
):
    root = tmp_path / "aios"
    root.mkdir()
    _receipt(monkeypatch, tmp_path, root)
    path = tmp_path / "authority-receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt[field] = value
    path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(RuntimeError, match="authority_preflight_receipt_identity_mismatch"):
        _verify_preflight_receipt(root, "contract-1", "permit-1", 123)
