#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "research/bc_queue.json"
STATE = ROOT / "research/bc_lifecycle_state.json"
PROMOTE = {"PROMOTE_TO_FUTURE_OOS_TEST"}


def load(p, default):
    return json.loads(p.read_text()) if p.exists() else default


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2))


def run_stage(name, script, state):
    print("RUN", name, script)
    p = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT,
                       text=True, capture_output=True)
    out = p.stdout + ("\n" + p.stderr if p.stderr else "")
    print(out, end="" if out.endswith("\n") else "\n")
    if p.returncode:
        state.update(status="BLOCKED", blocked_on=name, reason="audit_failed")
        save(STATE, state)
        return p.returncode, None
    decision = next((line.removeprefix("DECISION ").strip()
                     for line in reversed(out.splitlines())
                     if line.startswith("DECISION ")), None)
    state.setdefault("completed", [])
    if name not in state["completed"]:
        state["completed"].append(name)
    state["last_stage"] = name
    if decision:
        state["last_decision"] = decision
    save(STATE, state)
    return 0, decision


def failure_chain(candidate, queue, state, done):
    for item in queue.get("failure_analysis", {}).get(candidate, []):
        if item["name"] in done:
            continue
        rc, _ = run_stage(item["name"], item["audit_script"], state)
        if rc:
            return rc
        done.add(item["name"])
    return 0


def discovery(queue, state, done):
    rc, decision = run_stage("NEXT_HYPOTHESIS_DISCOVERY",
                             "audit_candidate_discovery.py", state)
    if rc:
        return rc
    if decision == "NO_VALIDATED_NEXT_HYPOTHESIS":
        state["status"] = "NO_VALIDATED_NEXT_HYPOTHESIS"
    else:
        state["status"] = "HYPOTHESIS_REGISTRATION_REQUIRED"
    save(STATE, state)
    print("LIFECYCLE_STOP", state["status"])
    return 0


def main():
    queue = load(QUEUE, {})
    state = load(STATE, {"schema_version": 3, "completed": [], "status": "READY"})
    done = set(state.get("completed", []))
    candidates = queue.get("candidates", [])
    pending = [x for x in candidates if x["name"] not in done]

    # If the registered queue is exhausted, never report the misleading
    # NO_PENDING state. First process the last rejected candidate's required
    # diagnostics, then run deterministic discovery. Discovery may register a
    # candidate only when its fixed, pre-OOS evidence rules are satisfied.
    if not pending:
        candidate = state.get("blocked_on") or state.get("last_candidate") or "BC5"
        last_decision = state.get("last_decision", "")
        if last_decision.startswith("REJECT_") or candidate in {x["name"] for x in candidates}:
            rc = failure_chain(candidate, queue, state, done)
            if rc:
                return rc
        return discovery(queue, state, done)

    for item in pending:
        name = item["name"]
        state["last_candidate"] = name
        save(STATE, state)
        rc, decision = run_stage(name, item["audit_script"], state)
        if rc:
            return rc
        done.add(name)

        if decision in PROMOTE:
            state.update(status="FROZEN_OOS_REQUIRED", blocked_on=name)
            save(STATE, state)
            print("LIFECYCLE_STOP", state["status"])
            return 0

        if decision and decision.startswith("REJECT_"):
            rc = failure_chain(name, queue, state, done)
            if rc:
                return rc
            return discovery(queue, state, done)

    return discovery(queue, state, done)


if __name__ == "__main__":
    raise SystemExit(main())
