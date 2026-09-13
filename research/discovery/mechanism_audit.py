#!/usr/bin/env python3
"""Fail-closed audit of trading-mechanism coverage.

This separates source discovery from actual deterministic translation. A family
cannot be reported executable merely because it appears in discovery metadata.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "research/discovery/trading_mechanism_registry.json"
OUT = ROOT / "research/discovery/mechanism_audit.json"


def audit() -> dict:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    families = registry["families"]
    counts = {}
    for item in families.values():
        status = item["status"]
        counts[status] = counts.get(status, 0) + 1
    executable = [k for k, v in families.items() if v["status"] in {"EXECUTABLE_FEATURES", "EXECUTABLE_EVENTS"}]
    blocked = [k for k, v in families.items() if v["status"] == "DATA_LANE_REQUIRED"]
    return {
        "schema_version": 1,
        "fail_closed": True,
        "total_families": len(families),
        "counts": counts,
        "executable_families": sorted(executable),
        "data_lane_required": sorted(blocked),
        "research_only": sorted(k for k, v in families.items() if v["status"] == "RESEARCH_ONLY"),
    }


def main() -> None:
    payload = audit()
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("MECHANISM_AUDIT", json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
