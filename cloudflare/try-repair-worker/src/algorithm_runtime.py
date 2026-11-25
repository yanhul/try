"""Closed-set algorithm runtime for the TRY Cloudflare Worker.

This module is intentionally pure: it accepts a declarative maze specification,
never imports caller code, and returns canonical artifact bytes. Durable dispatch,
permit authentication, and receipt issuance remain the responsibility of the
Worker/AIOS integration layer; this module alone grants no authority.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json

MAX_CELLS = 10_000
MAX_EXPANSIONS_HARD = 100_000
OPERATION = "maze.shortest_path"
VERSION = 1


class AlgorithmInputError(ValueError):
    pass


class AlgorithmBudgetExceeded(RuntimeError):
    pass


def canonical_json(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_request(value: dict) -> tuple[dict, tuple[str, ...], tuple[int, int], tuple[int, int]]:
    if not isinstance(value, dict) or set(value) != {"spec", "input"}:
        raise AlgorithmInputError("request_fields_invalid")
    spec = value["spec"]
    if not isinstance(spec, dict) or set(spec) - {"operation", "version", "max_expansions"}:
        raise AlgorithmInputError("spec_fields_invalid")
    if spec.get("operation") != OPERATION or type(spec.get("version", VERSION)) is not int or spec.get("version", VERSION) != VERSION:
        raise AlgorithmInputError("operation_unsupported")
    budget = spec.get("max_expansions", 100_000)
    if type(budget) is not int or not 1 <= budget <= MAX_EXPANSIONS_HARD:
        raise AlgorithmInputError("expansion_budget_invalid")
    data = value["input"]
    if not isinstance(data, dict) or set(data) != {"grid"}:
        raise AlgorithmInputError("input_fields_invalid")
    grid = data["grid"]
    if not isinstance(grid, list) or not grid or any(not isinstance(row, str) for row in grid):
        raise AlgorithmInputError("grid_invalid")
    width = len(grid[0])
    if width < 1 or any(len(row) != width for row in grid):
        raise AlgorithmInputError("grid_not_rectangular")
    if len(grid) * width > MAX_CELLS:
        raise AlgorithmInputError("grid_too_large")
    if any(cell not in "#.SG" for row in grid for cell in row):
        raise AlgorithmInputError("grid_cell_invalid")
    starts = [(r, c) for r, row in enumerate(grid) for c, cell in enumerate(row) if cell == "S"]
    goals = [(r, c) for r, row in enumerate(grid) for c, cell in enumerate(row) if cell == "G"]
    if len(starts) != 1 or len(goals) != 1:
        raise AlgorithmInputError("start_goal_cardinality_invalid")
    normalized = {
        "spec": {"operation": OPERATION, "version": VERSION, "max_expansions": budget},
        "input": {"grid": grid},
    }
    return normalized, tuple(grid), starts[0], goals[0]


def execute(value: dict) -> dict:
    normalized, grid, start, goal = validate_request(value)
    budget = normalized["spec"]["max_expansions"]
    height, width = len(grid), len(grid[0])
    queue = deque([start])
    parent = {start: None}
    expansions = 0
    # Stable operation-v1 tie-break order: north, east, south, west.
    neighbors = ((-1, 0), (0, 1), (1, 0), (0, -1))
    path = None
    while queue:
        current = queue.popleft()
        expansions += 1
        if expansions > budget:
            raise AlgorithmBudgetExceeded("expansion_budget_exceeded")
        if current == goal:
            reverse_path = []
            cursor = current
            while cursor is not None:
                reverse_path.append([cursor[0], cursor[1]])
                cursor = parent[cursor]
            path = list(reversed(reverse_path))
            break
        for dr, dc in neighbors:
            nxt = (current[0] + dr, current[1] + dc)
            if (0 <= nxt[0] < height and 0 <= nxt[1] < width
                    and grid[nxt[0]][nxt[1]] != "#" and nxt not in parent):
                parent[nxt] = current
                queue.append(nxt)
    artifact = {
        "schema": "try.algorithm-artifact.v1",
        "operation": OPERATION,
        "version": VERSION,
        "path": path,
        "expansions": expansions,
    }
    artifact_bytes = canonical_json(artifact)
    return {
        "spec_sha256": sha256_bytes(canonical_json(normalized["spec"])),
        "input_sha256": sha256_bytes(canonical_json(normalized["input"])),
        "artifact_sha256": sha256_bytes(artifact_bytes),
        "output_sha256": sha256_bytes(canonical_json(artifact)),
        "artifact_bytes": artifact_bytes,
        "artifact": artifact,
    }
