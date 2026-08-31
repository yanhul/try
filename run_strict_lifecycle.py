#!/usr/bin/env python3
"""Run the research lifecycle without manual BC-by-BC intervention.

Strict rules:
- OOS is never used for discovery or selection.
- A rejected candidate must go through failure analysis before discovery.
- Only candidates already registered by the repository's discovery mechanism are tested.
- No automatic hypothesis invention.
- A candidate must pass every required pre-OOS gate before the lifecycle can enter OOS.
- The controller stops only at a terminal state or a hard error.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "research" / "lifecycle_state.json"
PENDING = ROOT / "research" / "bc_pending_candidate.json"
QUEUE = ROOT / "research" / "bc_queue.json"
DISCOVERY = ROOT / "audit_candidate_discovery.py"
CANDIDATE_AUDIT = ROOT / "audit_candidate_feature.py"
FAILURE_AUDITS = [
    ROOT / "audit_bc4_1_failure_decomposition.py",
    ROOT / "audit_bc4_2_signal_quality.py",
]
MAX_ITERATIONS = int(os.environ.get("STRICT_MAX_ITERATIONS", "50"))


def load_state() -> dict:
    if not STATE.exists():
        return {"version": 1, "audited_candidates": [], "history": []}
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_script(path: Path) -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    out = p.stdout
    if p.stderr:
        out += ("\n" if out and not out.endswith("\n") else "") + p.stderr
    print(out, end="" if out.endswith("\n") else "\n")
    return p.returncode, out


def decision(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        if line.startswith("DECISION "):
            return line[len("DECISION "):].strip()
        if line.startswith("LIFECYCLE_STOP "):
            return line[len("LIFECYCLE_STOP "):].strip()
    return None


def candidate_name_from_pending() -> str:
    c = json.loads(PENDING.read_text(encoding="utf-8"))
    feature = c.get("feature")
    if not feature:
        raise RuntimeError("pending candidate has no feature")
    return "BC6_" + feature


def clear_pending() -> None:
    if PENDING.exists():
        PENDING.unlink()


def append_history(state: dict, item: dict) -> None:
    state.setdefault("history", []).append(item)
    # Keep the controller state bounded while preserving the full audit log elsewhere.
    state["history"] = state["history"][-200:]


def main() -> int:
    state = load_state()
    print("STRICT_LIFECYCLE_STATUS", {
        "oos_selection": False,
        "no_automatic_hypothesis_invention": True,
        "max_iterations": MAX_ITERATIONS,
    })

    for iteration in range(1, MAX_ITERATIONS + 1):
        print("LIFECYCLE_ITERATION", iteration)

        if PENDING.exists():
            name = candidate_name_from_pending()
            if name in state.get("audited_candidates", []):
                clear_pending()
                append_history(state, {"iteration": iteration, "candidate": name, "decision": "SKIP_ALREADY_AUDITED"})
                save_state(state)
                continue

            rc, out = run_script(CANDIDATE_AUDIT)
            if rc:
                return rc
            d = decision(out)
            if d is None:
                print("LIFECYCLE_STOP", "CANDIDATE_AUDIT_NO_DECISION")
                return 2

            state.setdefault("audited_candidates", []).append(name)
            append_history(state, {"iteration": iteration, "candidate": name, "decision": d})
            save_state(state)

            if d.startswith("PROMOTE_TO_FUTURE_OOS_TEST"):
                # This controller deliberately does not select/tune on OOS. A separate
                # frozen OOS runner must consume the immutable candidate definition.
                print("LIFECYCLE_TERMINAL", "FROZEN_CANDIDATE_READY_FOR_OOS")
                return 0

            clear_pending()
            print("FAILURE_ANALYSIS_REQUIRED", name)
            for audit in FAILURE_AUDITS:
                rc, _ = run_script(audit)
                if rc:
                    return rc
            continue

        rc, out = run_script(DISCOVERY)
        if rc:
            return rc
        d = decision(out)
        if d is None:
            print("LIFECYCLE_STOP", "DISCOVERY_NO_DECISION")
            return 2

        if d.startswith("REGISTERED_NEXT_CANDIDATE"):
            # Discovery wrote the pending candidate. Loop immediately; no manual step.
            continue

        if d == "NO_VALIDATED_NEXT_HYPOTHESIS":
            print("LIFECYCLE_TERMINAL", "EXHAUSTED")
            return 0

        if d.startswith("LIFECYCLE_STOP"):
            print("LIFECYCLE_TERMINAL", d)
            return 0

        print("LIFECYCLE_STOP", "UNEXPECTED_DECISION", d)
        return 2

    print("LIFECYCLE_TERMINAL", "RESEARCH_BUDGET_EXHAUSTED", {"max_iterations": MAX_ITERATIONS})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
