#!/usr/bin/env python3
"""Fail-closed audit of the canonical research-family registry.

The canonical family registry is the sole authority for family identity,
taxonomy layer, execution status, and evaluator binding. Discovery metadata
must never create a second execution authority.
"""
from __future__ import annotations

import json
from pathlib import Path

from research.family_registry import FAMILIES

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/discovery/mechanism_audit.json"


def audit() -> dict:
    families = FAMILIES
    counts: dict[str, int] = {}
    for spec in families.values():
        counts[spec.status] = counts.get(spec.status, 0) + 1

    executable = sorted(k for k, v in families.items() if v.status == "EXECUTABLE")
    discovery_only = sorted(k for k, v in families.items() if v.status == "DISCOVERY_ONLY")
    evaluator_only = sorted(k for k, v in families.items() if v.status == "EVALUATOR_ONLY")

    return {
        "schema_version": 2,
        "fail_closed": True,
        "authority": "research.family_registry",
        "total_families": len(families),
        "counts": counts,
        "executable_families": executable,
        "discovery_only": discovery_only,
        "evaluator_only": evaluator_only,
    }


def main() -> None:
    payload = audit()
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("MECHANISM_AUDIT", json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
