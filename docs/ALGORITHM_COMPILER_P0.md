# Verified Algorithm Executor — P0

## Scope

This is an isolated proof-of-concept in TRY. It demonstrates the engineering
pattern suggested by Looped Weight-Space Programming: a designer emits a small,
declarative algorithm specification; a bounded compiler maps a registered
operation to a deterministic executor; an independent verifier checks the
result; and a content-addressed receipt records the exact program/input/output
and verification decision. The receipt checksum is an unkeyed SHA-256 content
hash, not a signature or proof of origin.

## Trust boundaries

- The compiler accepts declarative data only. It does not `eval`, `exec`, import,
  or run LLM-generated source code.
- Only explicitly registered operations are compilable. P0 registers
  `maze.shortest_path` version 1.
- Execution has a hard grid-size ceiling and an explicit expansion budget.
- The executor's BFS and verifier's Dijkstra implementation are separate
  algorithms. The verifier checks endpoints, bounds, walls, adjacency and
  optimal path length, including the no-path case.
- A `VERIFIED` receipt applies only to the exact content-addressed input and
  program. It does not authorize side effects, registry promotion, or an
  `ABSORBED` capability state.
- AIOS remains the authority/evidence plane. This P0 does not call AIOS or write
  its capability registry; integration requires a separate contract, permit,
  immutable artifact lineage, conformance tests and explicit promotion gate.

## Run

```bash
python -m pytest -q tests/test_algorithm_compiler.py
```

## P0 exit criteria

- Deterministic registered operation and strict spec validation.
- Bounded execution and explicit budget failure.
- Independent shortest-path oracle.
- Content-addressed receipt with `VERIFIED` / `BLOCKED` and no implicit promotion.
- Tests cover normal, unreachable, 100x100, malformed, budget-exhaustion,
  non-optimal candidate and deterministic receipt cases.

This is not a reproduction of the MBZUAI Transformer, does not implement
weight-space programming, and makes no claim of 100% accuracy outside the
included tests.
