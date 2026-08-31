#!/usr/bin/env python3
"""Strict, resumable BC audit controller.

Runs only explicitly registered audit scripts. It never tunes or selects on OOS.
A terminal REJECT/FAILURE_ANALYSIS_REQUIRED state stops the cycle rather than
inventing a new hypothesis.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "research" / "bc_queue.json"
STATE = ROOT / "research" / "bc_lifecycle_state.json"

TERMINAL = {
    "REJECT_BC3",
    "REJECT_BC5",
    "REPORT_ONLY_NO_SELECTION",
    "NO_NEW_STRATEGY_UNTIL_FAILURE_ANALYSIS_IDENTIFIES_TESTABLE_CAUSE",
}
PROMOTE = {"PROMOTE_TO_FUTURE_OOS_TEST"}


def load(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def run_audit(script: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    output = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, output


def decision_from(output: str) -> str | None:
    for line in reversed(output.splitlines()):
        if line.startswith("DECISION "):
            return line.removeprefix("DECISION ").strip()
    return None


def main() -> int:
    queue = load(QUEUE, {"candidates": []})
    state = load(STATE, {"completed": [], "status": "READY"})

    for item in queue["candidates"]:
        name = item["name"]
        if name in state["completed"]:
            continue

        script = item["audit_script"]
        print("RUN", name, script)
        rc, output = run_audit(script)
        print(output, end="" if output.endswith("\n") else "\n")
        if rc != 0:
            state.update({"status": "BLOCKED", "blocked_on": name, "reason": "audit_failed"})
            save(STATE, state)
            return rc

        decision = decision_from(output)
        if decision is None:
            state.update({"status": "BLOCKED", "blocked_on": name, "reason": "missing_explicit_decision"})
            save(STATE, state)
            return 2

        state["completed"].append(name)
        state["last_decision"] = decision

        if decision in TERMINAL:
            state.update({"status": "FAILURE_ANALYSIS_REQUIRED", "blocked_on": name})
            save(STATE, state)
            print("LIFECYCLE_STOP", state["status"])
            return 0
        if decision in PROMOTE:
            state.update({"status": "FROZEN_OOS_REQUIRED", "blocked_on": name})
            save(STATE, state)
            print("LIFECYCLE_STOP", state["status"])
            return 0

        state["status"] = "READY"
        save(STATE, state)

    state["status"] = "NO_PENDING_REGISTERED_CANDIDATE"
    save(STATE, state)
    print("LIFECYCLE_STOP", state["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
