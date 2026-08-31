from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WalkForwardEvaluationPolicy:
    """Minimum evidence requirements for a research-grade walk-forward run."""

    min_test_bars: int = 500
    min_windows: int = 5
    min_total_test_bars: int = 2500


def validate_walk_forward_evidence(
    *,
    dataset_bars: int,
    train_size: int,
    test_size: int,
    step: int,
    window_count: int,
    policy: WalkForwardEvaluationPolicy = WalkForwardEvaluationPolicy(),
) -> None:
    """Reject WF configurations that are too small to support robustness claims.

    This is a research-evidence guard, not a trading-strategy rule. Small
    windows remain available for unit tests and exploratory debugging, but a
    research run must explicitly satisfy these minimum evidence requirements.
    """
    if dataset_bars <= 0:
        raise ValueError("dataset_bars must be positive")
    if train_size <= 0 or test_size <= 0 or step <= 0:
        raise ValueError("train_size, test_size, and step must be positive")
    if train_size + test_size > dataset_bars:
        raise ValueError("train_size + test_size exceeds dataset")
    if test_size < policy.min_test_bars:
        raise ValueError(
            f"test_size={test_size} is below research minimum "
            f"{policy.min_test_bars} bars"
        )
    if window_count < policy.min_windows:
        raise ValueError(
            f"window_count={window_count} is below research minimum "
            f"{policy.min_windows}"
        )
    if window_count * test_size < policy.min_total_test_bars:
        raise ValueError(
            "total test bars are below research minimum "
            f"{policy.min_total_test_bars}"
        )
