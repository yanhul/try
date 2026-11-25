# Verified Algorithm Executor — P0

## Scope

This is an isolated proof-of-concept in TRY. It demonstrates the engineering
pattern suggested by Looped Weight-Space Programming: a designer emits a small,
declarative algorithm specification; a bounded compiler maps a registered
operation to a deterministic executor; an independent verifier checks the
result; and a content-addressed receipt records the exact specification/input/output,
executor Git revision, executor source digest, and verification decision. The
receipt checksum is an unkeyed SHA-256 content hash, not a signature or proof
that a worker actually executed the source.

## Trust boundaries

- The compiler accepts declarative data only. It does not `eval`, `exec`, import,
  or run LLM-generated source code.
- Only explicitly registered operations are compilable. P0 registers
  `maze.shortest_path` version 1.
- Execution has a hard grid-size ceiling and an explicit expansion budget.
- The executor's BFS and verifier's Dijkstra implementation are separate
  algorithms. The verifier checks endpoints, bounds, walls, adjacency and
  optimal path length, including the no-path case.
- A `VERIFIED` receipt includes an executor source digest and full Git revision.
  The caller must compare both against pins supplied by the governing contract
  or deployment policy; values copied from the receipt are not trusted.
- AIOS independently checks the receipt with its own Dijkstra implementation.
  The contract, permit and HMAC attestation must verify; the contract must pin
  executor revision, source digest and specification digest, and explicitly
  allow the capability/effect. TRY's nested verification claim is informational only.
- AIOS returns `INDEPENDENTLY_VERIFIED`; promotion remains
  `NOT_AUTHORIZED`. No side effect, registry promotion, or `ABSORBED`
  capability state is authorized by this P0.
- AIOS remains the authority/evidence plane. The adapter delegates to the
  pinned AIOS checkout, verifies the execution contract/permit, and checks the
  exact input digest. It does not write the AIOS capability registry.

## Run

```bash
python -m pytest -q tests/test_algorithm_compiler.py
```

## P0 exit criteria

- Deterministic registered operation and strict spec validation.
- Bounded execution and explicit budget failure.
- Independent shortest-path oracle.
- Content-addressed receipt bound to executor revision/source digest.
- AIOS contract/permit integration and independent verification; no implicit promotion.
- Tests cover normal, unreachable, 100x100, malformed, budget-exhaustion,
  non-optimal candidate and deterministic receipt cases.

This is not a reproduction of the MBZUAI Transformer, does not implement
weight-space programming, and makes no claim of 100% accuracy outside the
included tests.
