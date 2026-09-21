from research import campaign_controller, repair_oos_evidence


def test_terminal_outcomes_are_fixed_by_policy_mapping():
    assert campaign_controller.QUALIFY == {
        "REJECT",
        "PROMOTE_TO_FUTURE_OOS_TEST",
    }
    assert "REJECT_BC" in campaign_controller.SCREENED_DECISIONS
    assert "REJECT_BC" not in campaign_controller.QUALIFY


def test_reject_bc_counts_as_screened_but_not_terminal_qualifying():
    history = [{"bc": 459, "decision": "REJECT_BC"}]
    assert campaign_controller.screened_bcs(history, start=1) == {459}
    assert campaign_controller.qualifying_bcs(history, start=1) == set()


def test_oos_pass_maps_to_edge_found():
    raw = "OOS_PASS"
    outcome = "EDGE_FOUND" if raw == "OOS_PASS" else "NO_EDGE_FOUND"
    assert outcome == "EDGE_FOUND"


def test_oos_fail_maps_to_no_edge_found():
    raw = "OOS_FAIL"
    outcome = "EDGE_FOUND" if raw == "OOS_PASS" else "NO_EDGE_FOUND"
    assert outcome == "NO_EDGE_FOUND"


def test_migrated_oos_marker_does_not_retarget_current_bc(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(repair_oos_evidence, "STATE", state_path)
    state_path.write_text(
        '{"campaign_terminal_reason":"OOS_FAIL_MIGRATED_TO_CANDIDATE_REJECTION","current_bc":251}\n',
        encoding="utf-8",
    )

    assert repair_oos_evidence.main() == 0
    assert "NOT_REQUIRED" in capsys.readouterr().out


def test_insufficient_oos_repair_evidence_fails_closed(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(repair_oos_evidence, "STATE", state_path)
    state_path.write_text(
        '{"campaign_terminal_reason":"OOS_FAIL","oos_failed_bc":251}\n',
        encoding="utf-8",
    )

    assert repair_oos_evidence.main() == 2
    assert "OOS_EVIDENCE_REPAIR_HOLD BC251" in capsys.readouterr().out
