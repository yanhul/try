# AIOS-CONTRACT: infrastructure/provider/evaluator failures cannot become task verdicts
# AIOS-REGRESSION: preserve failure-domain separation for autonomous research
# AIOS-OWNER: TRY research controller
# AIOS-COVERAGE-GAP: prior campaign outcomes could conflate execution failure with task failure
# AIOS-BASELINE: no strict outcome-domain validator existed for agentic execution
import pytest

from research.execution_outcome import (
    OutcomeClass,
    classify_outcome,
    is_infrastructure_failure,
    require_task_evaluation,
)


def test_infrastructure_failure_is_not_task_failure():
    record = {"outcome_class": OutcomeClass.PROVIDER_FAILURE.value}
    assert is_infrastructure_failure(record)
    with pytest.raises(ValueError, match="cannot be promoted"):
        require_task_evaluation(record)


def test_task_failure_is_evaluable():
    record = {"outcome_class": OutcomeClass.TASK_FAILURE.value}
    assert classify_outcome(record) is OutcomeClass.TASK_FAILURE
    assert require_task_evaluation(record) is OutcomeClass.TASK_FAILURE


def test_unknown_is_fail_closed():
    with pytest.raises(ValueError, match="cannot be promoted"):
        require_task_evaluation({"outcome_class": OutcomeClass.UNKNOWN.value})


def test_unauthorized_outcome_is_rejected():
    with pytest.raises(ValueError, match="unauthorized"):
        classify_outcome({"outcome_class": "PROMOTE"})
