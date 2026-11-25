import base64
import time
import os
import sys
from pathlib import Path
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from engine.aios_boundary import verify_algorithm_worker_receipt


@pytest.fixture
def aios_root():
    configured = os.environ.get("AIOS_ROOT") or os.environ.get("AIOS_SOURCE")
    if not configured:
        pytest.skip("AIOS_ROOT/AIOS_SOURCE is required for cross-repository conformance")
    root = Path(configured).resolve()
    if not (root / "core" / "algorithm_worker_receipt.py").is_file():
        pytest.fail(f"configured AIOS root lacks P1 verifier: {root}")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


@pytest.fixture
def provenance(aios_root):
    from core.algorithm_worker_receipt import (
        AlgorithmWorkerKeyring, RECEIPT_ISSUER, RECEIPT_SCOPE, SIGNED_FIELDS
    )
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    keyring = AlgorithmWorkerKeyring({RECEIPT_ISSUER: {
        "public_key": base64.b64encode(public).decode("ascii"),
        "key_id": "try-algorithm-worker-test-v1",
        "scopes": [RECEIPT_SCOPE], "revoked": False,
    }})
    expected = {
        "contract_id": "CT-ALGORITHM-1", "permit_id": "PM-ALGORITHM-1",
        "execution_id": "EX-ALGORITHM-1", "effect_id": "EF-ALGORITHM-1",
        "dispatch_id": "DP-ALGORITHM-1", "dispatch_digest": "8" * 64,
        "attempt_id": "EX-ALGORITHM-1:attempt:1",
        "attempt_number": 1, "worker_id": "try-algorithm-worker-ci",
        "worker_build_sha256": "a" * 64, "executor_revision": "b" * 40,
        "executor_sha256": "c" * 64, "spec_sha256": "d" * 64,
        "input_sha256": "e" * 64,
    }
    def sign(status="COMPLETED", **changes):
        now = time.time()
        body = {
            "type": "TRY_ALGORITHM_EXECUTION_RECEIPT_V1",
            "issuer": RECEIPT_ISSUER, "key_id": "try-algorithm-worker-test-v1",
            "receipt_id": "TA-" + "2" * 32, **expected,
            "artifact_sha256": "f" * 64 if status == "COMPLETED" else None,
            "output_sha256": "9" * 64 if status == "COMPLETED" else None,
            "status": status,
            "execution_state": "COMPLETED" if status == "COMPLETED" else "IN_PROGRESS_OR_AMBIGUOUS",
            "issued_at": now, "expires_at": now + 300, "algorithm": "Ed25519",
        }
        body.update(changes)
        signed = {field: body[field] for field in SIGNED_FIELDS}
        body["signature"] = base64.b64encode(
            private.sign(__import__("core.mutation", fromlist=["canonical_json"]).canonical_json(signed).encode("utf-8"))
        ).decode("ascii")
        return body
    return expected, keyring, sign


def test_try_boundary_delegates_signed_receipt_verification_to_aios(provenance, aios_root):
    expected, keyring, sign = provenance
    result = verify_algorithm_worker_receipt(
        sign(), expected=expected, keyring=keyring, aios_root=aios_root
    )
    assert result["status"] == "INDEPENDENTLY_AUTHENTICATED"
    assert result["worker_id"] == expected["worker_id"]
    assert result["retry_authorized"] is False
    assert result["promotion"] == "NOT_AUTHORIZED"


def test_try_boundary_preserves_unknown_without_retry(provenance, aios_root):
    expected, keyring, sign = provenance
    result = verify_algorithm_worker_receipt(
        sign("UNKNOWN"), expected=expected, keyring=keyring, aios_root=aios_root
    )
    assert result["status"] == "UNKNOWN"
    assert result["retry_authorized"] is False


def test_try_boundary_rejects_tampering_and_binding_substitution(provenance, aios_root):
    expected, keyring, sign = provenance
    tampered = sign()
    tampered["output_sha256"] = "0" * 64
    from core.algorithm_worker_receipt import AlgorithmWorkerReceiptError
    with pytest.raises(AlgorithmWorkerReceiptError, match="signature is invalid"):
        verify_algorithm_worker_receipt(tampered, expected=expected, keyring=keyring, aios_root=aios_root)
    with pytest.raises(AlgorithmWorkerReceiptError, match="attempt_number binding mismatch"):
        verify_algorithm_worker_receipt(sign(), expected=dict(expected, attempt_number=2), keyring=keyring, aios_root=aios_root)
