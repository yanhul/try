"""A deliberately small P0 for verified algorithm programs.

The compiler accepts declarative specifications only. It never evaluates LLM-
generated Python, imports user modules, or grants a program ambient authority.
The first registered operation is a deterministic maze shortest-path solver.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import heapq
import json
from typing import Any, Callable, Iterable


class AlgorithmSpecError(ValueError):
    """The declarative algorithm specification is invalid or unsupported."""


class ExecutionBudgetExceeded(RuntimeError):
    """The compiled operation exceeded its declared expansion budget."""


@dataclass(frozen=True)
class AlgorithmSpec:
    operation: str
    version: int = 1
    max_expansions: int = 100_000

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AlgorithmSpec":
        if not isinstance(value, dict):
            raise AlgorithmSpecError("spec must be an object")
        allowed = {"operation", "version", "max_expansions"}
        unknown = set(value) - allowed
        if unknown:
            raise AlgorithmSpecError(f"unknown spec fields: {sorted(unknown)}")
        operation = value.get("operation")
        version = value.get("version", 1)
        budget = value.get("max_expansions", 100_000)
        if not isinstance(operation, str) or not operation:
            raise AlgorithmSpecError("operation must be a non-empty string")
        if type(version) is not int or version != 1:
            raise AlgorithmSpecError("only integer spec version 1 is supported")
        if type(budget) is not int or not 1 <= budget <= 1_000_000:
            raise AlgorithmSpecError("max_expansions must be an integer in [1, 1000000]")
        return cls(operation=operation, version=version, max_expansions=budget)

    def canonical(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "version": self.version,
            "max_expansions": self.max_expansions,
        }


@dataclass(frozen=True)
class _Maze:
    rows: tuple[str, ...]
    start: tuple[int, int]
    goal: tuple[int, int]
    height: int
    width: int


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _parse_maze(grid: Iterable[str]) -> _Maze:
    if isinstance(grid, (str, bytes)):
        raise ValueError("grid must be an iterable of row strings, not one string")
    try:
        rows = tuple(grid)
    except TypeError as exc:
        raise ValueError("grid must be an iterable of row strings") from exc
    if not rows or any(not isinstance(row, str) for row in rows):
        raise ValueError("grid must contain at least one string row")
    width = len(rows[0])
    if width == 0 or any(len(row) != width for row in rows):
        raise ValueError("grid must be rectangular and non-empty")
    if len(rows) * width > 1_000_000:
        raise ValueError("grid exceeds the hard limit of 1,000,000 cells")
    if any(char not in "#.SG" for row in rows for char in row):
        raise ValueError("grid cells may contain only '#', '.', 'S', and 'G'")
    starts = [(r, c) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == "S"]
    goals = [(r, c) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == "G"]
    if len(starts) != 1 or len(goals) != 1:
        raise ValueError("grid must contain exactly one S and exactly one G")
    return _Maze(rows, starts[0], goals[0], len(rows), width)


# Stable tie-breaking is part of operation version 1.
_NEIGHBORS = ((-1, 0), (0, 1), (1, 0), (0, -1))
# The oracle intentionally defines its own traversal order to reduce shared code.
_ORACLE_NEIGHBORS = ((0, 1), (1, 0), (0, -1), (-1, 0))


def _bfs_shortest_path(maze: _Maze, max_expansions: int) -> dict[str, Any]:
    queue = deque([maze.start])
    parent: dict[tuple[int, int], tuple[int, int] | None] = {maze.start: None}
    expansions = 0
    while queue:
        current = queue.popleft()
        expansions += 1
        if expansions > max_expansions:
            raise ExecutionBudgetExceeded(
                f"maze.shortest_path exceeded max_expansions={max_expansions}"
            )
        if current == maze.goal:
            path = []
            cursor: tuple[int, int] | None = current
            while cursor is not None:
                path.append(cursor)
                cursor = parent[cursor]
            path.reverse()
            return {"path": [list(point) for point in path], "expansions": expansions}
        for dr, dc in _NEIGHBORS:
            nxt = (current[0] + dr, current[1] + dc)
            if (
                0 <= nxt[0] < maze.height
                and 0 <= nxt[1] < maze.width
                and maze.rows[nxt[0]][nxt[1]] != "#"
                and nxt not in parent
            ):
                parent[nxt] = current
                queue.append(nxt)
    return {"path": None, "expansions": expansions}


def _oracle_shortest_distance(maze: _Maze) -> int | None:
    """Independent Dijkstra oracle; intentionally does not share BFS state/code."""
    distances = {maze.start: 0}
    heap = [(0, maze.start)]
    while heap:
        distance, (row, col) = heapq.heappop(heap)
        point = (row, col)
        if distance != distances.get(point):
            continue
        if point == maze.goal:
            return distance
        for dr, dc in _ORACLE_NEIGHBORS:
            nxt = (row + dr, col + dc)
            if (
                0 <= nxt[0] < maze.height
                and 0 <= nxt[1] < maze.width
                and maze.rows[nxt[0]][nxt[1]] != "#"
            ):
                candidate = distance + 1
                if candidate < distances.get(nxt, 1 << 60):
                    distances[nxt] = candidate
                    heapq.heappush(heap, (candidate, nxt))
    return None


def compile_program(spec: AlgorithmSpec | dict[str, Any]) -> Callable[[Iterable[str]], dict[str, Any]]:
    """Compile a registered declarative operation into a bounded callable."""
    if isinstance(spec, dict):
        normalized = AlgorithmSpec.from_dict(spec)
    elif isinstance(spec, AlgorithmSpec):
        normalized = AlgorithmSpec.from_dict(spec.canonical())
    else:
        raise AlgorithmSpecError("spec must be AlgorithmSpec or a plain object")
    if normalized.version != 1:
        raise AlgorithmSpecError("unsupported algorithm spec version")
    if normalized.operation != "maze.shortest_path":
        raise AlgorithmSpecError(f"unsupported operation: {normalized.operation}")

    def run(grid: Iterable[str]) -> dict[str, Any]:
        maze = _parse_maze(grid)
        return _bfs_shortest_path(maze, normalized.max_expansions)

    return run


def verify_candidate(grid: Iterable[str], candidate: dict[str, Any]) -> dict[str, Any]:
    """Verify route validity and optimality with an independent Dijkstra oracle."""
    maze = _parse_maze(grid)
    if not isinstance(candidate, dict) or set(candidate) != {"path", "expansions"}:
        return {"verified": False, "reason": "candidate_schema_invalid", "oracle_distance": None}
    path = candidate["path"]
    if type(candidate["expansions"]) is not int or candidate["expansions"] < 0:
        return {"verified": False, "reason": "expansion_count_invalid", "oracle_distance": None}
    oracle_distance = _oracle_shortest_distance(maze)
    if path is None:
        ok = oracle_distance is None
        return {
            "verified": ok,
            "reason": "no_path_confirmed" if ok else "candidate_missed_existing_path",
            "oracle_distance": oracle_distance,
        }
    if not isinstance(path, list) or not path:
        return {"verified": False, "reason": "path_schema_invalid", "oracle_distance": oracle_distance}
    try:
        points = [tuple(point) for point in path]
    except TypeError:
        return {"verified": False, "reason": "path_schema_invalid", "oracle_distance": oracle_distance}
    if any(len(point) != 2 or any(type(v) is not int for v in point) for point in points):
        return {"verified": False, "reason": "coordinate_invalid", "oracle_distance": oracle_distance}
    if points[0] != maze.start or points[-1] != maze.goal:
        return {"verified": False, "reason": "endpoints_invalid", "oracle_distance": oracle_distance}
    for index, (row, col) in enumerate(points):
        if not (0 <= row < maze.height and 0 <= col < maze.width):
            return {"verified": False, "reason": "coordinate_out_of_bounds", "oracle_distance": oracle_distance}
        if maze.rows[row][col] == "#":
            return {"verified": False, "reason": "path_crosses_wall", "oracle_distance": oracle_distance}
        if index and abs(row - points[index - 1][0]) + abs(col - points[index - 1][1]) != 1:
            return {"verified": False, "reason": "non_adjacent_steps", "oracle_distance": oracle_distance}
    path_distance = len(points) - 1
    ok = oracle_distance is not None and path_distance == oracle_distance
    return {
        "verified": ok,
        "reason": "shortest_path_confirmed" if ok else "path_not_optimal_or_unreachable",
        "oracle_distance": oracle_distance,
        "candidate_distance": path_distance,
    }


def execute_and_verify(
    spec: AlgorithmSpec | dict[str, Any], grid: Iterable[str]
) -> dict[str, Any]:
    """Execute, independently verify, and emit a content-addressed evidence receipt.

    A verified receipt is evidence for this exact input/program pair only. It does
    not authorize registry promotion or confer authority on the compiled program.
    """
    if isinstance(spec, dict):
        normalized = AlgorithmSpec.from_dict(spec)
    elif isinstance(spec, AlgorithmSpec):
        normalized = AlgorithmSpec.from_dict(spec.canonical())
    else:
        raise AlgorithmSpecError("spec must be AlgorithmSpec or a plain object")
    maze = _parse_maze(grid)
    canonical_grid = list(maze.rows)
    candidate = compile_program(normalized)(canonical_grid)
    verification = verify_candidate(canonical_grid, candidate)
    receipt = {
        "schema": "try.algorithm-execution-receipt.v1",
        "program": normalized.canonical(),
        "program_sha256": _digest(normalized.canonical()),
        "input_sha256": _digest(canonical_grid),
        "candidate": candidate,
        "candidate_sha256": _digest(candidate),
        "verification": verification,
        "decision": "VERIFIED" if verification["verified"] else "BLOCKED",
        "promotion": "NOT_REQUESTED",
    }
    # Hash the canonical receipt before adding this checksum field.
    receipt["receipt_sha256"] = _digest(receipt)
    return receipt
