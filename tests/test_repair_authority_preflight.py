import hashlib
import json
import sys
import types
import shutil

from pathlib import Path
import pytest

from research.verify_repair_authority import _record_digest, verify_and_write_receipt


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


def _install_fake_aios(monkeypatch, *, attestation_ok=True, contract=None, permit=None, attestation=None):
    contract = contract if contract is not None else {
        "task_id": "try-ci-repair-12345",
        "actor": "try-autonomous-repair",
        "scope": "repository",
        "capabilities": ["repo_patch@1"],
        "allowed_effects": ["external_effect"],
        "max_attempts": 2,
    }
    permit = {"permit_id": "permit-1"} if permit is None else permit
    attestation = {"permit_id": "permit-1"} if attestation is None else attestation
    core = types.ModuleType("core")
    core.__path__ = []
    authority = types.ModuleType("core.authority")
    authority.authorize = lambda *args: True
    authority.load_contract = lambda *args: contract
    authority.load_permit = lambda *args: permit
    authority.load_attestation = lambda *args: attestation
    att = types.ModuleType("core.attestation")
    att.verify_attestation = lambda *args: attestation_ok
    core.authority = authority
    core.attestation = att
    monkeypatch.setitem(sys.modules, "core", core)
    monkeypatch.setitem(sys.modules, "core.authority", authority)
    monkeypatch.setitem(sys.modules, "core.attestation", att)


def _configure_preflight(monkeypatch, tmp_path, request):
    # The production gate intentionally rejects authority roots under /tmp;
    # keep the fixture inside the checked-out workspace and clean it afterward.
    root = Path.cwd() / f".test-durable-aios-{tmp_path.name}"
    shutil.rmtree(root, ignore_errors=True)
    request.addfinalizer(lambda: shutil.rmtree(root, ignore_errors=True))
    for kind, name in (
        ("contracts", "contract-1"),
        ("permits", "permit-1"),
        ("attestations", "permit-1"),
    ):
        path = root / "authority" / kind / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"id": name}), encoding="utf-8")
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_DIR", str(root))
    monkeypatch.setenv("AIOS_REPAIR_CONTRACT_ID", "contract-1")
    monkeypatch.setenv("AIOS_REPAIR_PERMIT_ID", "permit-1")
    monkeypatch.setenv("AIOS_REPAIR_ATTESTATION_SECRET", "test-only-secret")
    monkeypatch.setenv("AIOS_REPAIR_RUN_ID", "12345")
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_GATE_RECEIPT", str(runner_temp / "receipt.json"))
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    return root, runner_temp


def test_preflight_receipt_binds_run_and_exact_record_digests(monkeypatch, tmp_path, request):
    _install_fake_aios(monkeypatch)
    root, runner_temp = _configure_preflight(monkeypatch, tmp_path, request)
    receipt_path = verify_and_write_receipt()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["verified"] is True
    assert receipt["run_id"] == "12345"
    assert receipt["authority_root"] == str(root.resolve())
    assert receipt["contract_sha256"] == hashlib.sha256(
        (root / "authority/contracts/contract-1.json").read_bytes()
    ).hexdigest()
    assert receipt_path.parent == runner_temp.resolve()


def test_preflight_rejects_invalid_attestation(monkeypatch, tmp_path, request):
    _install_fake_aios(monkeypatch, attestation_ok=False)
    _configure_preflight(monkeypatch, tmp_path, request)
    with pytest.raises(RuntimeError, match="authority_attestation_rejected"):
        verify_and_write_receipt()


def test_preflight_rejects_contract_bound_to_another_run(monkeypatch, tmp_path, request):
    _install_fake_aios(monkeypatch, contract={
        "task_id": "try-ci-repair-99999",
        "actor": "try-autonomous-repair",
        "scope": "repository",
        "capabilities": ["repo_patch@1"],
        "allowed_effects": ["external_effect"],
        "max_attempts": 2,
    })
    _configure_preflight(monkeypatch, tmp_path, request)
    with pytest.raises(RuntimeError, match="contract_task_id_mismatch"):
        verify_and_write_receipt()


def test_preflight_rejects_receipt_outside_runner_temp(monkeypatch, tmp_path, request):
    _install_fake_aios(monkeypatch)
    _configure_preflight(monkeypatch, tmp_path, request)
    monkeypatch.setenv("AIOS_REPAIR_AUTHORITY_GATE_RECEIPT", str(tmp_path / "receipt.json"))
    with pytest.raises(RuntimeError, match="receipt_must_be_in_runner_temp"):
        verify_and_write_receipt()


def test_preflight_rejects_attempt_budget_above_runner_limit(monkeypatch, tmp_path, request):
    _install_fake_aios(monkeypatch, contract={
        "task_id": "try-ci-repair-12345",
        "actor": "try-autonomous-repair",
        "scope": "repository",
        "capabilities": ["repo_patch@1"],
        "allowed_effects": ["external_effect"],
        "max_attempts": 4,
    })
    _configure_preflight(monkeypatch, tmp_path, request)
    with pytest.raises(RuntimeError, match="contract_attempt_budget_exceeds_runner_limit"):
        verify_and_write_receipt()


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("AIOS_REPAIR_CONTRACT_ID", "../contract", "authority_contract_id_invalid"),
        ("AIOS_REPAIR_PERMIT_ID", "nested/permit", "authority_permit_id_invalid"),
    ],
)
def test_preflight_rejects_path_like_authority_ids_before_aios_load(
    monkeypatch, tmp_path, request, variable, value, message
):
    _install_fake_aios(monkeypatch)
    _configure_preflight(monkeypatch, tmp_path, request)
    monkeypatch.setenv(variable, value)
    with pytest.raises(RuntimeError, match=message):
        verify_and_write_receipt()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("capabilities", "repo_patch@1", "contract_capabilities_type_invalid"),
        ("capabilities", ["repo_patch@1", 7], "contract_capabilities_type_invalid"),
        ("allowed_effects", "external_effect", "contract_allowed_effects_type_invalid"),
        ("allowed_effects", ["external_effect", False], "contract_allowed_effects_type_invalid"),
    ],
)
def test_preflight_rejects_malformed_contract_authority_lists(
    monkeypatch, tmp_path, request, field, value, message
):
    contract = {
        "task_id": "try-ci-repair-12345",
        "actor": "try-autonomous-repair",
        "scope": "repository",
        "capabilities": ["repo_patch@1"],
        "allowed_effects": ["external_effect"],
        "max_attempts": 2,
    }
    contract[field] = value
    _install_fake_aios(monkeypatch, contract=contract)
    _configure_preflight(monkeypatch, tmp_path, request)
    with pytest.raises(RuntimeError, match=message):
        verify_and_write_receipt()



@pytest.mark.parametrize(
    ("record_name", "record_value", "message"),
    [
        ("contract", None, "contract_record_type_invalid"),
        ("permit", [], "permit_record_type_invalid"),
        ("attestation", "not-a-record", "attestation_record_type_invalid"),
    ],
)
def test_preflight_rejects_non_mapping_authority_records_before_verification(
    monkeypatch, tmp_path, request, record_name, record_value, message
):
    kwargs = {record_name: record_value}
    _install_fake_aios(monkeypatch, **kwargs)
    _configure_preflight(monkeypatch, tmp_path, request)
    with pytest.raises(RuntimeError, match=message):
        verify_and_write_receipt()
