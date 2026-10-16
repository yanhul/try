"""Regression tests for strict AIOS terminal evidence resolution.

The AIOS evidence verifier is injected to keep these tests isolated from a
particular AIOS checkout while exercising TRY's resolver and on-disk lineage.
"""
import json
import sys
import types
from pathlib import Path

from research.autonomous_repair import resolve_terminal_evidence


BASE_SHA = "a" * 40
RUN_ID = 123456
EFFECT_ID = "EF-19a9d8fd83e2d963fc2f1861079aab816d18dcf1357759b1467455dab21c5295"


def _record(evidence_id, *, run_id=str(RUN_ID), source_ref=None,
            artifact_ref=None, claim="pytest verification passed",
            level="VERIFIED_DIGITAL", parent_evidence_id=None):
    return {
        "evidence_id": evidence_id,
        "level": level,
        "source_ref": source_ref or f"github:yanhul/try@{BASE_SHA}",
        "artifact_ref": artifact_ref,
        "claim": claim,
        "run_id": run_id,
        "provider": "github-actions",
        "parent_evidence_id": parent_evidence_id,
        "digest": "ok",
    }


def _setup(monkeypatch, tmp_path, evidence_records):
    core = types.ModuleType("core")
    evidence_module = types.ModuleType("core.evidence")
    evidence_module.verify_evidence = lambda record: record.get("digest") == "ok"
    effect_authority = types.ModuleType("core.effect_authority")
    def validate_persisted_effect(_root, effect):
        if (effect.get("record_type") != "EXTERNAL_EFFECT"
                or effect.get("policy_digest") != "policy-digest"
                or effect.get("max_attempts") != 3
                or effect.get("attempt") > effect.get("max_attempts")):
            raise ValueError("persisted effect invalid")
    effect_authority._validate_persisted_effect = validate_persisted_effect
    core.evidence = evidence_module
    monkeypatch.setitem(sys.modules, "core", core)
    monkeypatch.setitem(sys.modules, "core.evidence", evidence_module)
    monkeypatch.setitem(sys.modules, "core.effect_authority", effect_authority)

    root = tmp_path / "aios"
    (root / "effects").mkdir(parents=True)
    (root / "evidence").mkdir()
    attempt_id = f"{EFFECT_ID}:attempt:1"
    effect = {
        "record_type": "EXTERNAL_EFFECT",
        "effect_id": EFFECT_ID,
        "logical_operation_id": "try-ci-repair:123456:1",
        "state": "OBSERVED_SUCCESS",
        "contract_id": "contract-1",
        "permit_id": "permit-1",
        "actor": "try-autonomous-repair",
        "effect_type": "external_effect",
        "policy_digest": "policy-digest",
        "max_attempts": 3,
        "attempt": 1,
        "attempt_id": attempt_id,
        "provider": "github-actions",
        "provider_observation": {
            "attempt_id": attempt_id,
            "provider": "github-actions",
            "evidence": {
                "provider": "github-actions",
                "run_id": attempt_id,
                "digest": "ok",
            },
        },
    }
    (root / "effects" / f"{EFFECT_ID}.json").write_text(
        json.dumps(effect), encoding="utf-8"
    )
    for evidence_id, record in evidence_records.items():
        (root / "evidence" / f"{evidence_id}.json").write_text(
            json.dumps(record), encoding="utf-8"
        )
    return root


def _resolve(root, refs):
    return resolve_terminal_evidence(
        root, refs, run_id=RUN_ID, base_sha=BASE_SHA, applied={"effect_id": EFFECT_ID, "attempt_id": f"{EFFECT_ID}:attempt:1", "provider": "github-actions", "outcome": "OBSERVED_SUCCESS"},
        contract_id="contract-1", permit_id="permit-1",
    )


def test_accepts_digest_verified_evidence_bound_to_exact_run_and_base(monkeypatch, tmp_path):
    root = _setup(monkeypatch, tmp_path, {"EV-good": _record("EV-good")})
    assert _resolve(root, ["EV-good"]) is None



def test_rejects_effect_record_with_tampered_logical_identity(monkeypatch, tmp_path):
    root = _setup(monkeypatch, tmp_path, {"EV-good": _record("EV-good")})
    path = root / "effects" / f"{EFFECT_ID}.json"
    effect = json.loads(path.read_text(encoding="utf-8"))
    effect["logical_operation_id"] = "attacker-substituted-operation"
    path.write_text(json.dumps(effect), encoding="utf-8")
    assert "effect_identity_digest_mismatch" in _resolve(root, ["EV-good"])


def test_rejects_effect_with_noncanonical_attempt_id(monkeypatch, tmp_path):
    root = _setup(monkeypatch, tmp_path, {"EV-good": _record("EV-good")})
    path = root / "effects" / f"{EFFECT_ID}.json"
    effect = json.loads(path.read_text(encoding="utf-8"))
    effect["attempt_id"] = "attempt-7"
    effect["provider_observation"]["attempt_id"] = "attempt-7"
    effect["provider_observation"]["evidence"]["run_id"] = "attempt-7"
    path.write_text(json.dumps(effect), encoding="utf-8")
    assert "effect_attempt_identity_mismatch" in resolve_terminal_evidence(
        root, ["EV-good"], run_id=RUN_ID, base_sha=BASE_SHA,
        applied={"effect_id": EFFECT_ID, "attempt_id": "attempt-7", "provider": "github-actions", "outcome": "OBSERVED_SUCCESS"},
        contract_id="contract-1", permit_id="permit-1",
    )


def test_rejects_effect_attempt_budget_tampering(monkeypatch, tmp_path):
    root = _setup(monkeypatch, tmp_path, {"EV-good": _record("EV-good")})
    path = root / "effects" / f"{EFFECT_ID}.json"
    effect = json.loads(path.read_text(encoding="utf-8"))
    effect["max_attempts"] = True
    path.write_text(json.dumps(effect), encoding="utf-8")
    assert "effect_attempt_budget_invalid" in _resolve(root, ["EV-good"])



def test_rejects_base_sha_embedded_inside_longer_hex_token(monkeypatch, tmp_path):
    record = _record("EV-false", source_ref="build:" + ("c" + BASE_SHA))
    root = _setup(monkeypatch, tmp_path, {"EV-false": record})
    assert "base_sha_lineage_missing" in _resolve(root, ["EV-false"])


def test_rejects_duplicate_evidence_refs(monkeypatch, tmp_path):
    root = _setup(monkeypatch, tmp_path, {"EV-good": _record("EV-good")})
    assert "duplicate_evidence_refs" in _resolve(root, ["EV-good", "EV-good"])


def test_rejects_evidence_symlink_escape(monkeypatch, tmp_path):
    root = _setup(monkeypatch, tmp_path, {})
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(_record("EV-link")), encoding="utf-8")
    (root / "evidence" / "EV-link.json").symlink_to(outside)
    assert "record_unavailable_or_invalid" in _resolve(root, ["EV-link"])


def test_rejects_parent_with_wrong_run_or_base_lineage(monkeypatch, tmp_path):
    child = _record("EV-child", parent_evidence_id="EV-parent")
    parent = _record("EV-parent", source_ref="github:yanhul/try@deadbeef")
    root = _setup(monkeypatch, tmp_path, {"EV-child": child, "EV-parent": parent})
    assert "parent_base_sha_lineage_missing" in _resolve(root, ["EV-child"])

def test_rejects_parent_evidence_cycle(monkeypatch, tmp_path):
    child = _record("EV-child", parent_evidence_id="EV-parent")
    parent = _record("EV-parent", parent_evidence_id="EV-child")
    root = _setup(monkeypatch, tmp_path, {"EV-child": child, "EV-parent": parent})
    assert "parent_evidence_cycle" in _resolve(root, ["EV-child"])

def test_rejects_persisted_effect_symlink_escape(monkeypatch, tmp_path):
    root = _setup(monkeypatch, tmp_path, {"EV-good": _record("EV-good")})
    effect_path = root / "effects" / f"{EFFECT_ID}.json"
    effect_path.unlink()
    outside = tmp_path / "outside-effect.json"
    outside.write_text(json.dumps({
        "effect_id": EFFECT_ID, "state": "OBSERVED_SUCCESS",
        "contract_id": "contract-1", "permit_id": "permit-1",
        "actor": "try-autonomous-repair", "attempt_id": "attempt-7",
        "provider": "github-actions",
        "provider_observation": {
            "attempt_id": "attempt-7", "provider": "github-actions",
            "evidence": {"provider": "github-actions", "run_id": "attempt-7", "digest": "ok"},
        },
    }), encoding="utf-8")
    effect_path.symlink_to(outside)
    assert "persisted_effect_path_escape" in _resolve(root, ["EV-good"])

def test_rejects_evidence_directory_symlink_escape(monkeypatch, tmp_path):
    root = _setup(monkeypatch, tmp_path, {"EV-good": _record("EV-good")})
    evidence_dir = root / "evidence"
    evidence_dir.rename(tmp_path / "evidence-real")
    evidence_dir.symlink_to(tmp_path / "evidence-real", target_is_directory=True)
    assert "evidence_directory_escape" in _resolve(root, ["EV-good"])


def test_rejects_effects_directory_symlink_escape(monkeypatch, tmp_path):
    root = _setup(monkeypatch, tmp_path, {"EV-good": _record("EV-good")})
    effects_dir = root / "effects"
    effects_dir.rename(tmp_path / "effects-real")
    effects_dir.symlink_to(tmp_path / "effects-real", target_is_directory=True)
    assert "persisted_effect_directory_escape" in _resolve(root, ["EV-good"])


def test_rejects_claim_that_only_contains_test_as_substring(monkeypatch, tmp_path):
    record = _record("EV-contest", claim="contest completed successfully")
    root = _setup(monkeypatch, tmp_path, {"EV-contest": record})
    assert "claim_not_test_verification" in _resolve(root, ["EV-contest"])
