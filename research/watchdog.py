#!/usr/bin/env python3
"""Independent health watchdog for the durable research controller.

This is operational monitoring only. It does not change research policy,
budget, evidence requirements, promotion criteria, or terminal outcomes.
A controller schedule of */15 minutes implies two missed wake windows = 30
minutes as the stale threshold.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "research" / "bc_lifecycle_state.json"
SCHEDULE_MINUTES = 15
STALE_AFTER = timedelta(minutes=SCHEDULE_MINUTES * 2)


def now():
    return datetime.now(timezone.utc)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> int:
    if not STATE.exists():
        print("WATCHDOG_ALERT reason=STATE_MISSING")
        return 2

    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"WATCHDOG_ALERT reason=STATE_UNREADABLE error={exc}")
        return 2

    if state.get("terminal") or state.get("campaign_terminal"):
        print("WATCHDOG_OK reason=TERMINAL")
        return 0

    raw = state.get("updated_at")
    if not raw:
        print("WATCHDOG_ALERT reason=UPDATED_AT_MISSING")
        return 2

    try:
        updated = parse_timestamp(raw)
    except Exception as exc:
        print(f"WATCHDOG_ALERT reason=UPDATED_AT_INVALID error={exc}")
        return 2

    age = now() - updated
    age_seconds = int(age.total_seconds())
    print(
        f"WATCHDOG_CHECK updated_at={raw} age_seconds={age_seconds} "
        f"threshold_seconds={int(STALE_AFTER.total_seconds())} "
        f"phase={state.get('phase')} retry_count={state.get('retry_count', 0)}"
    )

    if age > STALE_AFTER:
        reason = "STALE_NONTERMINAL_STATE"
        print(
            f"WATCHDOG_ALERT reason={reason} age_seconds={age_seconds} "
            f"phase={state.get('phase')} current_bc={state.get('current_bc')}"
        )
        return 1

    print("WATCHDOG_OK reason=FRESH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
