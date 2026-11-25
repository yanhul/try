import base64
import hashlib
import os
import sys
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from engine.aios_boundary import verify_algorithm_worker_artifact


@pytest.fixture
def artifact_case():
    configured = os.environ.get("AIOS_ROOT") or os.environ.get("AIOS_SOURCE")
    if not configured:
        pytest.skip("AIOS_ROOT/AIOS_SOURCE required for cross-repository verification")
    root = Path(configured).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from core.mutation import canonical_json
    from core.algorithm_worker_receipt import RECEIPT_ISSUER, SIGNED_FIELDS

    grid = ["S..", ".#.", "..G"]
    spec = {"operation": "maze.shortest_path", "version": 1, "max_expansions": 100}
    artifact = {
        "schema": "try.algorithm-artifact.v1", "operation": "maze.shortest_path",
        "version": 1, "path": [[0, 0], [0, 1], [0, 2], [1, 2], [2, 2]],
        "expansions": 8,
    }
    artifact_bytes = canonical_json(artifact).encode("utf-8")
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    keyring = __import__("core.algorithm_worker_receipt", fromlist=["AlgorithmWorkerKeyring"]).AlgorithmWorkerKeyring({
        RECEIPT_ISSUER: {
            "public_key": base64.b64encode(public).decode("ascii"),
            "key_id": "try-worker-artifact-test-v1",
            "scopes": ["try.algorithm.execution.receipt.verify"],
            "revoked": False,
        }
    })
    expected = {
        "contract_id": "CT-1", "permit_id": "PM-1", "execution_id": "EX-1",
        "effect_id": "EF-1", "dispatch_id": "DP-1", "dispatch_digest": "8" * 64,
        "attempt_id": "EX-1:attempt:1", "attempt_number": 1,
        "worker_id": "try-worker-test", "worker_build_sha256": "a" * 64,
        "executor_revision": "b" * 40, "executor_sha256": "c" * 64,
        "spec_sha256": hashlib.sha256(canonical_json(spec).encode()).hexdigest(),
        "input_sha256": hashlib.sha256(canonical_json({"grid": grid}).encode()).hexdigest(),
    }
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    now = time.time()
    receipt = {
        "type": "TRY_ALGORITHM_EXECUTION_RECEIPT_V1", "issuer": RECEIPT_ISSUER,
        "key_id": "try-worker-artifact-test-v1", "receipt_id": "TA-" + "1" * 32,
        **expected, "artifact_sha256": digest, "output_sha256": digest,
        "status": "COMPLETED", "execution_state": "COMPLETED",
        "issued_at": now, "expires_at": now + 300, "algorithm": "Ed25519",
    }
    signed = {field: receipt[field] for field in SIGNED_FIELDS}
    receipt["signature"] = base64.b64encode(
        private.sign(canonical_json(signed).encode("utf-8"))
    ).decode("ascii")
    return receipt, artifact_bytes, expected, grid, spec, keyring


def test_try_boundary_delegates_exact_bytes_and_independent_oracle(artifact_case):
    receipt, artifact_bytes, expected, grid, spec, keyring = artifact_case
    result = verify_algorithm_worker_artifact(
        receipt, artifact_bytes, expected=expected, grid=grid, spec=spec,
        expected_executor_revision="b" * 40, expected_executor_sha256="c" * 64,
        keyring=keyring,
    )
    assert result["status"] == "INDEPENDENTLY_VERIFIED"
    assert result["oracle_distance"] == 4
    assert result["retry_authorized"] is False
    assert result["promotion"] == "NOT_AUTHORIZED"


def test_try_boundary_rejects_artifact_bytes_not_bound_by_worker_signature(artifact_case):
    receipt, artifact_bytes, expected, grid, spec, keyring = artifact_case
    with pytest.raises(ValueError, match="artifact bytes do not match"):
        verify_algorithm_worker_artifact(
            receipt, artifact_bytes + b" ", expected=expected, grid=grid, spec=spec,
            expected_executor_revision="b" * 40, expected_executor_sha256="c" * 64,
            keyring=keyring,
        )
