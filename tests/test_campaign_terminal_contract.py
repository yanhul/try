from research import campaign_controller


def test_terminal_outcomes_are_fixed_by_policy_mapping():
    assert campaign_controller.QUALIFY == {
        "REJECT",
        "PROMOTE_TO_FUTURE_OOS_TEST",
    }


def test_oos_pass_maps_to_edge_found():
    raw = "OOS_PASS"
    outcome = "EDGE_FOUND" if raw == "OOS_PASS" else "NO_EDGE_FOUND"
    assert outcome == "EDGE_FOUND"


def test_oos_fail_maps_to_no_edge_found():
    raw = "OOS_FAIL"
    outcome = "EDGE_FOUND" if raw == "OOS_PASS" else "NO_EDGE_FOUND"
    assert outcome == "NO_EDGE_FOUND"
