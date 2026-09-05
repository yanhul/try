import pytest

from research.evidence_calibration import parse_verdict, verification_prompt


def test_pass_requires_empty_issues():
    assert parse_verdict('{"status":"PASS","issues":[]}') == (True, [])


def test_pass_with_issues_is_rejected():
    with pytest.raises(ValueError, match="pass_with_issues"):
        parse_verdict('{"status":"PASS","issues":[{"code":"X","claim":"c","reason":"r"}]}')


def test_fail_preserves_structured_issue():
    ok, issues = parse_verdict(
        '{"status":"FAIL","issues":[{"code":"OVERCLAIM","claim":"C excludes large effects","reason":"no CI supplied"}]}'
    )
    assert not ok
    assert issues == [{"code": "OVERCLAIM", "claim": "C excludes large effects", "reason": "no CI supplied"}]


def test_invalid_status_fails_closed():
    with pytest.raises(ValueError, match="invalid_calibration_verdict"):
        parse_verdict('{"status":"MAYBE","issues":[]}')


def test_verification_prompt_contains_exact_candidate_and_artifact():
    prompt = verification_prompt({"rationale": "test", "evidence_sources": ["C"]}, "artifact-C")
    assert '"rationale": "test"' in prompt
    assert '"evidence_sources": ["C"]' in prompt
    assert "artifact-C" in prompt
