#!/usr/bin/env python3
"""Strict, resumable BC research state machine.

A single invocation advances through registered audits and, after a rejected
candidate, automatically runs the registered failure-analysis chain. It never
creates an unregistered hypothesis, tunes parameters, or uses OOS for
selection. State is persisted after every stage so reruns resume safely.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "research" / "bc_queue.json"
STATE = ROOT / "research" / "bc_lifecycle_state.json"

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
    return proc.returncode, proc.stdout + ("\n" + proc.stderr if proc.stderr else "")


def decision_from(output: str) -> str | None:
    for line in reversed(output.splitlines()):
        if line.startswith("DECISION "):
            return line.removeprefix("DECISION ").strip()
    return None


def run_stage(name: str, script: str, state: dict) -> tuple[int, str | None]:
    print("RUN", name, script)
    rc, output = run_audit(script)
    print(output, end="" if output.endswith("\n") else "\n")
    if rc != 0:
        state.update({"status": "BLOCKED", "blocked_on": name, "reason": "audit_failed"})
        save(STATE, state)
        return rc, None
    decision = decision_from(output)
    if decision is not None:
        state["last_decision"] = decision
    state.setdefault("completed", []).append(name)
    state["last_stage"] = name
    save(STATE, state)
    return 0, decision


def main() -> int:
    queue = load(QUEUE, {})
    state = load(STATE, {"schema_version": 2, "completed": [], "status": "READY"})
    completed = set(state.get("completed", []))

    # Normal candidate audits.
    for item in queue.get("candidates", []):
        name, script = item["name"], item["audit_script"]
        if name in completed:
            continue
        rc, decision = run_stage(name, script, state)
        if rc:
            return rc
        completed.add(name)

        if decision in PROMOTE:
            state.update({"status": "FROZEN_OOS_REQUIRED", "blocked_on": name})
            save(STATE, state)
            print("LIFECYCLE_STOP", state["status"])
            return 0

        if decision and decision.startswith("REJECT_"):
            # Rejects automatically enter the explicit failure-analysis chain.
            analyses = queue.get("failure_analysis", {}).get(name, [])
            if not analyses:
                state.update({
                    "status": "FAILURE_ANALYSIS_REQUIRED",
                    "blocked_on": name,
                    "reason": "no_registered_failure_analysis_chain",
                })
                save(STATE, state)
                print("LIFECYCLE_STOP", state["status"])
                return 0
            for analysis in analyses:
                aname, ascript = analysis["name"], analysis["audit_script"]
                if aname in completed:
                    continue
                rc, _ = run_stage(aname, ascript, state)
                if rc:
                    return rc
                completed.add(aname)
            state.update({
                "status": "HYPOTHESIS_REGISTRATION_REQUIRED",
                "blocked_on": name,
                "reason": "failure_analysis_completed_but_no_new_hypothesis_was_automatically_invented",
            })
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
