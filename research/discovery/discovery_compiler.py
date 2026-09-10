#!/usr/bin/env python3
"""Compile only registered, deterministic primitives; never invent unavailable columns."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "research/discovery/primitive_registry.json"
AUDIT = ROOT / "research/discovery/source_audit.json"
OUT = ROOT / "research/discovery/compiled_candidates.json"
BUDGET = 100


def candidate(expr: dict) -> dict:
    raw = json.dumps(expr, sort_keys=True, separators=(",", ":"))
    return {**expr, "candidate_id": "disc-" + hashlib.sha256(raw.encode()).hexdigest()[:16]}


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8")) if AUDIT.exists() else {"available_columns": []}
    available = set(audit.get("available_columns", []))
    columns = [c for c in registry["columns"] if c in available]
    ops = registry["operators"]
    windows = registry["windows"]
    out = []

    def add(x):
        if len(out) < BUDGET:
            out.append(candidate(x))

    for col in columns:
        add({"operator":"identity","left":col})
    for op in ("zscore", "rolling_mean", "rolling_std", "lag", "delta", "rank"):
        if op not in ops:
            continue
        for col in columns:
            for w in windows:
                add({"operator":op,"left":col,"window":w})
    for op in ("ratio", "difference"):
        if op not in ops:
            continue
        for i, left in enumerate(columns):
            for right in columns[i + 1:]:
                for w in windows:
                    add({"operator":op,"left":left,"right":right,"window":w})

    OUT.write_text(json.dumps({
        "schema_version": 1,
        "budget": BUDGET,
        "available_columns": sorted(available),
        "candidate_count": len(out),
        "candidates": out,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"DISCOVERY_COMPILED {len(out)}/{BUDGET}")


if __name__ == "__main__":
    main()
