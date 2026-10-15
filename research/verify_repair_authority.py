"""Safe hashing of AIOS authority records used by repair preflight."""
from __future__ import annotations

import hashlib
from pathlib import Path

_ALLOWED_RECORD_KINDS = frozenset({"contracts", "permits", "decisions", "evidence", "receipts", "executions", "mutations"})


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _record_digest(aios_root, kind: str, record_id: str) -> str:
    if not isinstance(kind, str) or kind not in _ALLOWED_RECORD_KINDS:
        raise RuntimeError("authority_record_kind_invalid")
    if (
        not isinstance(record_id, str)
        or not record_id
        or record_id in {".", ".."}
        or "/" in record_id
        or "\\" in record_id
        or len(record_id) > 128
    ):
        raise RuntimeError("authority_record_id_invalid")

    root = Path(aios_root).resolve()
    authority = root / "authority"
    authority_resolved = authority.resolve()
    if not _inside(authority_resolved, root):
        raise RuntimeError("authority_directory_path_escape")
    if not authority_resolved.is_dir():
        raise RuntimeError("authority_directory_missing")

    records_dir = authority_resolved / kind
    records_resolved = records_dir.resolve()
    if not _inside(records_resolved, authority_resolved):
        raise RuntimeError("authority_record_directory_escape")
    if not records_resolved.is_dir():
        raise RuntimeError("authority_record_directory_missing")

    record = records_resolved / f"{record_id}.json"
    record_resolved = record.resolve()
    if not _inside(record_resolved, records_resolved):
        raise RuntimeError("authority_record_path_escape")
    if not record_resolved.is_file():
        raise RuntimeError("authority_record_missing")
    return hashlib.sha256(record_resolved.read_bytes()).hexdigest()
