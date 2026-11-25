import pytest

from engine.algorithm_compiler import (
    AlgorithmSpec,
    ExecutionBudgetExceeded,
    compile_program,
    execute_and_verify,
    verify_candidate,
)


def test_compiles_and_verifies_shortest_path():
    grid = ["S..", ".#.", "..G"]
    receipt = execute_and_verify({"operation": "maze.shortest_path"}, grid, executor_revision="a".repeat(40))
    assert receipt["decision"] == "VERIFIED"
    assert receipt["verification"]["oracle_distance"] == 4
    assert receipt["promotion"] == "NOT_REQUESTED"
    assert len(receipt["receipt_sha256"]) == 64


def test_scales_to_100_by_100_without_retraining_or_parameter_growth():
    grid = ["S" + "." * 99] + ["." * 100 for _ in range(98)] + ["." * 99 + "G"]
    receipt = execute_and_verify({"operation": "maze.shortest_path", "max_expansions": 10_000}, grid, executor_revision="a".repeat(40))
    assert receipt["decision"] == "VERIFIED"
    assert receipt["verification"]["oracle_distance"] == 198
    assert receipt["candidate"]["expansions"] <= 10_000


def test_confirms_unreachable_maze():
    receipt = execute_and_verify({"operation": "maze.shortest_path"}, ["S#G"], executor_revision="a".repeat(40))
    assert receipt["decision"] == "VERIFIED"
    assert receipt["candidate"]["path"] is None
    assert receipt["verification"]["reason"] == "no_path_confirmed"


def test_rejects_unknown_operation_and_unknown_fields():
    with pytest.raises(ValueError, match="unsupported operation"):
        compile_program({"operation": "python.eval"})
    with pytest.raises(ValueError, match="unknown spec fields"):
        AlgorithmSpec.from_dict({"operation": "maze.shortest_path", "source": "print(1)"})


def test_rejects_invalid_maze_and_invalid_budget():
    with pytest.raises(ValueError, match="exactly one S"):
        compile_program({"operation": "maze.shortest_path"})(["..."])
    with pytest.raises(ValueError, match="max_expansions"):
        AlgorithmSpec.from_dict({"operation": "maze.shortest_path", "max_expansions": 0})


def test_execution_budget_is_enforced():
    with pytest.raises(ExecutionBudgetExceeded):
        compile_program({"operation": "maze.shortest_path", "max_expansions": 1})(["S..", "...", "..G"])


def test_independent_verifier_rejects_non_shortest_candidate():
    grid = ["S..", "...", "..G"]
    candidate = {"path": [[0, 0], [0, 1], [1, 1], [1, 0], [2, 0], [2, 1], [2, 2]], "expansions": 7}
    report = verify_candidate(grid, candidate)
    assert report["verified"] is False
    assert report["reason"] == "path_not_optimal_or_unreachable"


def test_rejects_invalid_direct_dataclass_construction():
    with pytest.raises(ValueError, match="max_expansions"):
        compile_program(AlgorithmSpec("maze.shortest_path", max_expansions=0))


def test_receipt_hash_is_deterministic_for_same_program_and_input():
    spec = {"operation": "maze.shortest_path"}
    grid = ["S..", ".#.", "..G"]
    first = execute_and_verify(spec, grid, executor_revision="a".repeat(40))
    second = execute_and_verify(spec, grid, executor_revision="a".repeat(40))
    assert first["receipt_sha256"] == second["receipt_sha256"]



def test_receipt_binds_executor_revision_and_source_digest():
    from engine.algorithm_compiler import executor_source_sha256
    receipt = execute_and_verify(
        {"operation": "maze.shortest_path"}, ["SG"],
        executor_revision="a" * 40,
    )
    assert receipt["executor_revision"] == "a" * 40
    assert receipt["executor_sha256"] == executor_source_sha256()


def test_executor_revision_must_be_full_git_sha():
    with pytest.raises(ValueError, match="full lowercase Git commit SHA"):
        execute_and_verify({"operation": "maze.shortest_path"}, ["SG"], executor_revision="main")
