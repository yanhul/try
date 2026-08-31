from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from autonomous_hypothesis import load_candidate, write_candidate

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "research" / "bc_lifecycle_state.json"
QUEUE = ROOT / "research" / "bc_queue.json"
FAILURE_DIR = ROOT / "research" / "failure_analysis"
CANDIDATE_DIR = ROOT / "research" / "autonomous_candidates"
PROMOTE = "PROMOTE_TO_FUTURE_OOS_TEST"
REJECT = "REJECT_BC"
DEFAULT_MAX_ITERATIONS = 8


def run(cmd):
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    out = p.stdout + p.stderr
    print(out, end="")
    return p.returncode, out


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"oos_consumed": [], "terminal": False, "last_bc": None, "iterations": 0, "history": []}


def save_state(s):
    s["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(s, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_queue():
    if not QUEUE.exists():
        return []
    value = json.loads(QUEUE.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("bc_queue.json must be a list")
    return value


def queue_candidate(candidate):
    queue = load_queue()
    if any(x.get("candidate_hash") == candidate["candidate_hash"] for x in queue):
        return False
    queue.append(candidate)
    QUEUE.write_text(json.dumps(queue, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def next_bc(queue, state):
    if queue:
        return max(int(x["bc"]) for x in queue) + 1
    last = state.get("last_bc")
    return int(last) + 1 if last is not None else 1


def generate_candidate(parent_bc: int, state: dict):
    """Ask an explicitly configured research agent to generate exactly one candidate.

    The controller itself never invents a strategy. Without an agent command it
    stops at HOLD rather than fabricating a hypothesis.
    """
    command = os.environ.get("RESEARCH_AGENT_COMMAND", "").strip()
    if not command:
        print("CONTROLLER_DECISION HOLD_NO_RESEARCH_AGENT")
        return None
    failure = FAILURE_DIR / f"BC{parent_bc}.json"
    if not failure.exists():
        print(f"CONTROLLER_DECISION HOLD_NO_FAILURE_ANALYSIS BC{parent_bc}")
        return None
    bc = next_bc(load_queue(), state)
    output = CANDIDATE_DIR / f"BC{bc}.json"
    env = os.environ.copy()
    env.update({"RESEARCH_PARENT_BC": str(parent_bc), "RESEARCH_NEXT_BC": str(bc),
                "RESEARCH_FAILURE_ANALYSIS": str(failure), "RESEARCH_CANDIDATE_OUTPUT": str(output)})
    print(f"CONTROLLER_AGENT BC{bc} parent=BC{parent_bc}")
    p = subprocess.run(shlex.split(command), cwd=ROOT, text=True, capture_output=True, env=env)
    print(p.stdout, end="")
    print(p.stderr, end="")
    if p.returncode:
        print(f"CONTROLLER_DECISION HOLD_AGENT_FAILURE rc={p.returncode}")
        return None
    try:
        candidate = load_candidate(output, bc, parent_bc)
    except Exception as exc:
        print(f"CONTROLLER_DECISION BLOCKED_INVALID_HYPOTHESIS reason={exc}")
        return None
    write_candidate(output, candidate)
    if not queue_candidate(candidate):
        print(f"CONTROLLER_DECISION HOLD_DUPLICATE_CANDIDATE hash={candidate['candidate_hash']}")
        return None
    print(f"CONTROLLER_REGISTERED BC{bc} hash={candidate['candidate_hash']}")
    return candidate


def gate_for(bc: int):
    gate = ROOT / f"audit_bc{bc}_fast_gate.py"
    return gate if gate.exists() else None


def run_oos(bc, state):
    if bc in state["oos_consumed"]:
        print(f"CONTROLLER_DECISION BC{bc}_OOS_ALREADY_CONSUMED")
        return 6
    oos = ROOT / f"audit_bc{bc}_future_oos.py"
    if not oos.exists():
        print(f"CONTROLLER_DECISION BC{bc}_PROMOTED_BUT_NO_FROZEN_OOS_AUDIT")
        return 3
    print(f"CONTROLLER_BC{bc}_OOS START frozen=1 selection=0 one_shot=1")
    rc, out = run([sys.executable, oos.name])
    state["oos_consumed"].append(bc)
    state["last_bc"] = bc
    save_state(state)
    if rc:
        return rc
    if "REPORT_ONLY" not in out:
        print("CONTROLLER_DECISION BLOCKED_OOS_NOT_REPORT_ONLY")
        return 4
    print(f"CONTROLLER_BC{bc}_OOS REPORT_ONLY")
    print("CONTROLLER_NEXT_STEP FINAL_REPORT_REVIEW")
    return 0


def main():
    state = load_state()
    max_iterations = int(os.environ.get("RESEARCH_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS))
    print(f"BC_CONTROLLER_START strict=1 autonomous=1 oos_selection=0 max_iterations={max_iterations}")
    if state.get("terminal"):
        print("CONTROLLER_DECISION TERMINAL_STATE")
        return 0

    rc, _ = run([sys.executable, "-m", "pytest"])
    if rc:
        print("CONTROLLER_DECISION BLOCKED_TEST_FAILURE")
        return rc

    for _ in range(max_iterations):
        queue = load_queue()
        if not queue:
            print("CONTROLLER_DECISION HOLD_EMPTY_QUEUE")
            return 0
        candidate = queue[-1]
        bc = int(candidate["bc"])
        gate = gate_for(bc)
        if gate is None:
            print(f"CONTROLLER_DECISION HOLD_NO_GATE BC{bc}")
            return 0
        state["last_bc"] = bc
        state["iterations"] = int(state.get("iterations", 0)) + 1
        save_state(state)
        print(f"CONTROLLER_CANDIDATE BC{bc} GATE {gate.name}")
        rc, out = run([sys.executable, gate.name])
        if rc:
            print(f"CONTROLLER_DECISION BC{bc}_SCRIPT_FAILURE")
            return rc
        if PROMOTE in out:
            return run_oos(bc, state)
        if REJECT in out or "SPLIT_GATE False" in out:
            print(f"CONTROLLER_BC{bc} REJECT_OR_GATE_FAIL")
            candidate = generate_candidate(bc, state)
            if candidate is None:
                state["history"].append({"bc": bc, "decision": "REJECT", "next": "HOLD_OR_EXHAUSTED"})
                save_state(state)
                return 0
            continue
        print(f"CONTROLLER_DECISION BC{bc}_NO_EXPLICIT_DECISION_BLOCKED")
        return 5

    print(f"CONTROLLER_DECISION EXHAUSTED_MAX_ITERATIONS={max_iterations}")
    state["terminal"] = True
    state["terminal_reason"] = "max_iterations"
    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
