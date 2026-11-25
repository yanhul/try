"""Bounded, declarative algorithm compilation and independent verification."""

from .program import (
    AlgorithmSpec,
    AlgorithmSpecError,
    ExecutionBudgetExceeded,
    compile_program,
    execute_and_verify,
    verify_candidate,
)

__all__ = [
    "AlgorithmSpec",
    "AlgorithmSpecError",
    "ExecutionBudgetExceeded",
    "compile_program",
    "execute_and_verify",
    "verify_candidate",
]
