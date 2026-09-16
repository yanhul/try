from research import campaign_controller, repair_oos_evidence


def test_oos_fail_requires_explicit_failed_bc(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(repair_oos_evidence, "STATE", state_path)
    state_path.write_text(
        '{"campaign_terminal_reason":"OOS_FAIL","current_bc":999}\n',
        encoding="utf-8",
    )
    assert repair_oos_evidence.main() == 2
    assert "missing_oos_failed_bc" in capsys.readouterr().out


def test_migrated_oos_marker_is_not_a_repair_request(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(repair_oos_evidence, "STATE", state_path)
    state_path.write_text(
        '{"campaign_terminal_reason":"OOS_FAIL_MIGRATED_TO_CANDIDATE_REJECTION","current_bc":999}\n',
        encoding="utf-8",
    )
    assert repair_oos_evidence.main() == 0
    assert "NOT_REQUIRED" in capsys.readouterr().out


def test_migration_uses_explicit_failed_bc_not_current_cursor(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    candidate_dir = tmp_path / "candidates"
    failure_dir = tmp_path / "failures"
    oos_dir = tmp_path / "oos"
    candidate_dir.mkdir()
    oos_dir.mkdir()
    monkeypatch.setattr(campaign_controller, "STATE", state_path)
    monkeypatch.setattr(campaign_controller, "CANDIDATE_DIR", candidate_dir)
    monkeypatch.setattr(campaign_controller, "FAILURE_DIR", failure_dir)
    monkeypatch.setattr(campaign_controller, "OOS_DIR", oos_dir)
    candidate_hash = "hash-247"
    (candidate_dir / "BC247.json").write_text(
        '{"bc":247,"parent_bc":246,"candidate_hash":"hash-247","hypothesis_id":"h247"}\n',
        encoding="utf-8",
    )
    result = {
        "bc": 247, "candidate_hash": candidate_hash, "oos_executed": True,
        "oos_selection_used": False, "oos_passed": False,
        "metrics": {"pf": 0.8}, "dataset": {"sha256": "data"},
        "protocol_sha256": "protocol",
    }
    import json
    (oos_dir / "BC247_oos_result.json").write_text(json.dumps(result), encoding="utf-8")
    receipt = {
        "receipt_type": "OOS_EXECUTION_RECEIPT", "schema_version": 1, "bc": 247,
        "candidate_hash": candidate_hash, "oos_executed": True,
        "oos_selection_used": False, "oos_passed": False,
        "metrics": {"pf": 0.8}, "dataset_sha256": "data", "protocol_sha256": "protocol",
    }
    (oos_dir / "BC247_oos_result_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    state_path.write_text(
        '{"campaign_terminal":true,"campaign_terminal_reason":"OOS_FAIL",'
        '"oos_failed_bc":247,"current_bc":999,"next_bc":999}\n', encoding="utf-8"
    )
    state = campaign_controller.load(state_path, {})
    assert campaign_controller._migrate_candidate_oos_terminal(state) is True
    assert (failure_dir / "BC247.json").exists()
    assert not (failure_dir / "BC999.json").exists()
    assert "BC247" in capsys.readouterr().out


def test_oos_repair_failure_prevents_controller_execution(tmp_path):
    """Mirror GitHub Actions fail-fast sequencing using the real repair entrypoint."""
    state_path = tmp_path / "state.json"
    marker = tmp_path / "controller-ran"
    state_path.write_text(
        '{"campaign_terminal_reason":"OOS_FAIL","current_bc":999}\n',
        encoding="utf-8",
    )
    repair_script = tmp_path / "run_repair.py"
    repair_script.write_text(
        "from pathlib import Path\n"
        "from research import repair_oos_evidence\n"
        f"repair_oos_evidence.STATE = Path(r'{state_path}')\n"
        "raise SystemExit(repair_oos_evidence.main())\n",
        encoding="utf-8",
    )
    marker_script = tmp_path / "mark_controller.py"
    marker_script.write_text(
        "from pathlib import Path\n"
        f"Path(r'{marker}').write_text('ran')\n",
        encoding="utf-8",
    )
    import os
    import subprocess
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    result = subprocess.run(
        ["bash", "-c", f"set -e; python '{repair_script}'; python '{marker_script}'"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 2
    assert not marker.exists()
