import hashlib
from pathlib import Path

import pytest

from research.verify_repair_authority import _record_digest


def test_record_digest_hashes_exact_record_bytes(tmp_path):
    root = tmp_path / "aios"
    record_dir = root / "authority" / "contracts"
    record_dir.mkdir(parents=True)
    record = record_dir / "contract-1.json"
    record.write_bytes(b'{"contract_id":"contract-1"}')
    assert _record_digest(root, "contracts", "contract-1") == hashlib.sha256(record.read_bytes()).hexdigest()


def test_record_digest_rejects_authority_root_symlink_escape(tmp_path):
    root = tmp_path / "aios"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "contracts").mkdir()
    (root / "authority").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="authority_directory_path_escape"):
        _record_digest(root, "contracts", "contract-1")


def test_record_digest_rejects_record_directory_symlink_escape(tmp_path):
    root = tmp_path / "aios"
    authority = root / "authority"
    authority.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "contract-1.json").write_text("{}", encoding="utf-8")
    (authority / "contracts").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="authority_record_directory_escape"):
        _record_digest(root, "contracts", "contract-1")


@pytest.mark.parametrize("record_id", ["../outside", "nested/contract", "", ".", "x" * 129])
def test_record_digest_rejects_path_like_or_overlong_ids(tmp_path, record_id):
    with pytest.raises(RuntimeError, match="authority_record_id_invalid"):
        _record_digest(tmp_path, "contracts", record_id)


def test_record_digest_rejects_unknown_record_kind(tmp_path):
    with pytest.raises(RuntimeError, match="authority_record_kind_invalid"):
        _record_digest(tmp_path, "secrets", "contract-1")
