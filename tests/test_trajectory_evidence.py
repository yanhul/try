# AIOS-CONTRACT: raw provider output precedes normalization, evaluation and credit
# AIOS-REGRESSION: infra/unknown outcomes cannot receive task credit
# AIOS-OWNER: TRY research trajectory attribution
# AIOS-COVERAGE-GAP: campaign evidence lacked step-level raw/normalized attribution
# AIOS-BASELINE: no strict trajectory evidence primitive existed
import pytest
from research.trajectory_evidence import StepEvidence, DiagnosticIntervention, validate_step, require_credit_inputs

def make(outcome="TASK_SUCCESS"):
    return StepEvidence("traj:1","step:1","attempt:2",'{"tool":"search"}',
        ({"name":"search","args":{}},),outcome,"int:1")

def test_round_trip_and_independent_digests():
    r=make().as_record()
    assert validate_step(r).evidence_digest==r["evidence_digest"]
    assert r["raw_output_digest"]!=r["normalized_digest"]

def test_raw_tamper_rejected():
    r=make().as_record(); r["raw_output"]='{"tool":"evil"}'
    with pytest.raises(ValueError,match="raw output digest"): validate_step(r)

def test_normalized_tamper_rejected():
    r=make().as_record(); r["normalized_tool_calls"]=[{"name":"evil"}]
    with pytest.raises(ValueError,match="normalized digest"): validate_step(r)

def test_unknown_not_creditable():
    with pytest.raises(ValueError,match="not creditable"):
        require_credit_inputs(make("UNKNOWN").as_record())

def test_diagnostic_intervention_is_explicit():
    x=DiagnosticIntervention("int:1","tool-call cap isolates provider failure",{"max_tool_calls":2})
    assert x.as_record()["intervention_id"]=="int:1"
