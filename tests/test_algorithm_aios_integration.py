import hashlib
import os
import sys
from pathlib import Path

import pytest

from engine.aios_boundary import verify_authorized_algorithm_receipt
from engine.algorithm_compiler import execute_and_verify, executor_source_sha256


GRID = ["S..", ".#.", "..G"]
SPEC = {"operation": "maze.shortest_path", "version": 1, "max_expansions": 1000}
EXECUTOR_REVISION = "a" * 40
ATTESTATION_SECRET = "test-only-aios-permit-attestation-secret"


@pytest.fixture
def aios_root():
    configured = os.environ.get("AIOS_ROOT") or os.environ.get("AIOS_SOURCE")
    if not configured:
        pytest.skip("AIOS_ROOT/AIOS_SOURCE is required for cross-repository conformance")
    root = Path(configured).resolve()
    if not (root / "core" / "contract.py").is_file():
        pytest.fail(f"configured AIOS root is incomplete: {root}")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def _contract_and_permit(aios_root, *, capabilities=None, effects=None, input_digest=None,
                          include_pins=True):
    from core.attestation import issue_attestation
    from core.contract import issue_permit
    from core.mutation import canonical_json

    source_digest = executor_source_sha256()
    spec_digest = hashlib.sha256(canonical_json(SPEC).encode("utf-8")).hexdigest()
    grid_digest = hashlib.sha256(canonical_json(GRID).encode("utf-8")).hexdigest()
    predicates = []
    if include_pins:
        predicates = [
            {"predicate_id": "algorithm-executor-revision", "path": "receipt.executor_revision",
             "operator": "eq", "expected": EXECUTOR_REVISION},
            {"predicate_id": "algorithm-executor-source", "path": "receipt.executor_sha256",
             "operator": "eq", "expected": source_digest},
            {"predicate_id": "algorithm-specification", "path": "receipt.spec_sha256",
             "operator": "eq", "expected": spec_digest},
        ]
    contract = {
        "contract_type": "EXECUTION_CONTRACT",
        "task_id": "ALGORITHM_MAZE_P0",
        "scope": "algorithm_execution",
        "actor": "try-algorithm-worker",
        "capabilities": capabilities if capabilities is not None else ["algorithm_execute"],
        "input_digest": input_digest if input_digest is not None else "sha256:" + grid_digest,
        "allowed_effects": effects if effects is not None else ["compute_algorithm"],
        "evidence_required": ["aios_independent_algorithm_receipt"],
        "max_attempts": 1,
        "terminal_states": ["VERIFIED", "BLOCKED", "UNKNOWN"],
        "policy_digest": "sha256:" + "c" * 64,
        "acceptance_predicates": predicates,
    }
    permit = issue_permit(contract, "external-aios-authority")
    attestation = issue_attestation(contract, permit, ATTESTATION_SECRET)
    return contract, permit, attestation


def _run(aios_root, contract=None, permit=None, attestation=None):
    receipt = execute_and_verify(SPEC, GRID, executor_revision=EXECUTOR_REVISION)
    if contract is None or permit is None or attestation is None:
        contract, permit, attestation = _contract_and_permit(aios_root)
    return verify_authorized_algorithm_receipt(
        contract,
        permit,
        receipt,
        grid=GRID,
        spec=receipt["spec"],
        expected_executor_revision=EXECUTOR_REVISION,
        expected_executor_sha256=executor_source_sha256(),
        attestation=attestation,
        attestation_secret=ATTESTATION_SECRET,
        aios_root=aios_root,
    )


def test_aios_attested_contract_permit_and_independent_receipt_verification(aios_root):
    contract, permit, attestation = _contract_and_permit(aios_root)
    result = _run(aios_root, contract, permit, attestation)
    assert result["status"] == "INDEPENDENTLY_VERIFIED"
    assert result["oracle_distance"] == 4
    assert result["authority"] == "AIOS.core.contract+core.algorithm_execution_receipt"
    assert result["promotion"] == "NOT_AUTHORIZED"


def test_contract_without_algorithm_capability_is_rejected(aios_root):
    contract, permit, attestation = _contract_and_permit(aios_root, capabilities=["research_execute"])
    with pytest.raises(PermissionError, match="does not grant algorithm_execute"):
        _run(aios_root, contract, permit, attestation)


def test_contract_without_compute_effect_is_rejected(aios_root):
    contract, permit, attestation = _contract_and_permit(aios_root, effects=["write_research_evidence"])
    with pytest.raises(PermissionError, match="does not allow compute_algorithm"):
        _run(aios_root, contract, permit, attestation)


def test_permit_mutation_is_rejected(aios_root):
    contract, permit, attestation = _contract_and_permit(aios_root)
    permit["capabilities"] = ["algorithm_execute", "live_trade"]
    with pytest.raises(ValueError):
        _run(aios_root, contract, permit, attestation)


def test_contract_input_digest_mismatch_is_rejected(aios_root):
    contract, permit, attestation = _contract_and_permit(
        aios_root, input_digest="sha256:" + "d" * 64
    )
    with pytest.raises(ValueError, match="input_digest does not bind"):
        _run(aios_root, contract, permit, attestation)


def test_contract_must_pin_executor_revision_source_and_spec(aios_root):
    contract, permit, attestation = _contract_and_permit(aios_root, include_pins=False)
    with pytest.raises(PermissionError, match="does not pin algorithm-executor-revision"):
        _run(aios_root, contract, permit, attestation)


def test_unsigned_or_tampered_attestation_is_rejected(aios_root):
    contract, permit, attestation = _contract_and_permit(aios_root)
    attestation["signature"] = "0" * 64
    with pytest.raises(ValueError):
        _run(aios_root, contract, permit, attestation)
