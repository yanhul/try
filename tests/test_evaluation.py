import pytest

from engine.evaluation import validate_walk_forward_evidence


def test_research_wf_guard_accepts_sufficient_evidence():
    validate_walk_forward_evidence(
        dataset_bars=3624,
        train_size=1600,
        test_size=500,
        step=500,
        window_count=5,
    )


def test_research_wf_guard_rejects_tiny_test_windows():
    with pytest.raises(ValueError, match="test_size"):
        validate_walk_forward_evidence(
            dataset_bars=40,
            train_size=20,
            test_size=10,
            step=10,
            window_count=2,
        )


def test_research_wf_guard_rejects_too_few_windows():
    with pytest.raises(ValueError, match="window_count"):
        validate_walk_forward_evidence(
            dataset_bars=2000,
            train_size=1000,
            test_size=500,
            step=500,
            window_count=2,
        )
