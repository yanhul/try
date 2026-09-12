from research.autonomous_hypothesis import canonical_hash, validate_candidate


def base():
    return {
        "bc": 6,
        "parent_bc": 5,
        "hypothesis_id": "h6",
        "conceptual_change": "change one signal filter",
        "evidence_sources": ["research/failure_analysis/BC5.json"],
        "rationale": "repeatable diagnostic cause in IS and validation",
        "is_testable": True,
        "oos_selection_used": False,
    }


def test_valid_candidate_gets_immutable_hash():
    c = base()
    ok, digest = validate_candidate(c, 6, 5)
    assert ok
    assert c["candidate_hash"] == digest == canonical_hash(c)


def test_rejects_multiple_conceptual_changes():
    c = base()
    c["conceptual_change"] = ["change A", "change B"]
    ok, reason = validate_candidate(c, 6, 5)
    assert not ok
    assert reason == "exactly_one_conceptual_change_required"


def test_rejects_oos_selection():
    c = base()
    c["oos_selection_used"] = True
    ok, reason = validate_candidate(c, 6, 5)
    assert not ok
    assert reason == "oos_selection_forbidden"


def test_rejects_missing_evidence():
    c = base()
    c["evidence_sources"] = []
    ok, reason = validate_candidate(c, 6, 5)
    assert not ok
    assert reason == "evidence_sources_required"


def test_rejects_nonfinite_threshold():
    c = base()
    c["discovery_spec"] = {"operator": "identity", "left": "close", "threshold": float("nan"), "direction": "above"}
    ok, reason = validate_candidate(c, 6, 5)
    assert not ok
    assert reason == "invalid_discovery_threshold"


def test_rejects_boolean_threshold():
    c = base()
    c["discovery_spec"] = {"operator": "identity", "left": "close", "threshold": True, "direction": "above"}
    ok, reason = validate_candidate(c, 6, 5)
    assert not ok
    assert reason == "invalid_discovery_threshold"


def test_discovered_primitive_requires_executable_spec():
    c = base()
    c["hypothesis_id"] = "discovered_primitive"
    ok, reason = validate_candidate(c, 6, 5)
    assert not ok
    assert reason == "discovery_spec_required"


def test_discovered_primitive_accepts_valid_spec():
    c = base()
    c["hypothesis_id"] = "discovered_primitive"
    c["discovery_spec"] = {
        "operator": "zscore",
        "left": "close",
        "window": 20,
        "threshold": 1.0,
        "direction": "above",
    }
    ok, digest = validate_candidate(c, 6, 5)
    assert ok
    assert c["candidate_hash"] == digest
