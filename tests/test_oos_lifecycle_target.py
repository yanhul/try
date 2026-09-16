from research import repair_oos_evidence


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
