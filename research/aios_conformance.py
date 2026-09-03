#!/usr/bin/env python3
"""Fail-closed conformance gate for the child research harness."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = {
    "research/RESEARCH_GUARD.md": (
        "Validated datasets are immutable",
        "OOS is read-only and excluded from parameter search",
        "Regression/parity failures block experiments",
    ),
    "research/bc_controller.py": (
        "checkpoint(s,'OBSERVE'",
        "checkpoint(s,'DECIDE'",
        "checkpoint(s,'VERIFY'",
        "checkpoint(s,'PERSISTED'",
        "terminal",
    ),
}


def main() -> int:
    failures = []
    for rel, needles in REQUIRED.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                failures.append(f"{rel}: missing invariant: {needle}")
    if failures:
        print("AIOS_CONFORMANCE: BLOCKED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("AIOS_CONFORMANCE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
