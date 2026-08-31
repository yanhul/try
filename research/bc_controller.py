from __future__ import annotations
import json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "research" / "bc_lifecycle_state.json"
FAST_GATE = re.compile(r"audit_bc(\d+)_fast_gate\.py$")
PROMOTE = "PROMOTE_TO_FUTURE_OOS_TEST"
REJECT = "REJECT_BC"

def run(cmd):
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    out = p.stdout + p.stderr
    print(out, end="")
    return p.returncode, out

def gates():
    found = []
    for p in ROOT.glob("audit_bc*_fast_gate.py"):
        m = FAST_GATE.match(p.name)
        if m:
            found.append((int(m.group(1)), p))
    return sorted(found)

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"oos_consumed": [], "terminal": False, "last_bc": None}

def save_state(s):
    s["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(s, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def main():
    state = load_state()
    print("BC_CONTROLLER_START strict=1 oos_selection=0 resumable=1")

    if state.get("terminal"):
        print("CONTROLLER_DECISION TERMINAL_STATE")
        return 0

    rc, _ = run([sys.executable, "-m", "pytest"])
    if rc:
        print("CONTROLLER_DECISION BLOCKED_TEST_FAILURE")
        return rc

    gs = gates()
    if not gs:
        print("CONTROLLER_DECISION NO_CANDIDATE_GATES")
        return 0

    bc, gate = gs[-1]
    print(f"CONTROLLER_CANDIDATE BC{bc} GATE {gate.name}")

    rc, out = run([sys.executable, gate.name])
    if rc:
        print(f"CONTROLLER_DECISION BC{bc}_SCRIPT_FAILURE")
        return rc

    if PROMOTE in out:
        if bc in state["oos_consumed"]:
            print(f"CONTROLLER_DECISION BC{bc}_OOS_ALREADY_CONSUMED")
            return 6
        oos = ROOT / f"audit_bc{bc}_future_oos.py"
        if not oos.exists():
            print(f"CONTROLLER_DECISION BC{bc}_PROMOTED_BUT_NO_FROZEN_OOS_AUDIT")
            return 3
        print(f"CONTROLLER_BC{bc}_OOS START frozen=1 selection=0 one_shot=1")
        rc, oos_out = run([sys.executable, oos.name])
        state["oos_consumed"].append(bc)
        state["last_bc"] = bc
        save_state(state)
        if rc:
            print(f"CONTROLLER_DECISION BC{bc}_OOS_SCRIPT_FAILURE")
            return rc
        if "REPORT_ONLY" not in oos_out:
            print("CONTROLLER_DECISION BLOCKED_OOS_NOT_REPORT_ONLY")
            return 4
        print(f"CONTROLLER_BC{bc}_OOS REPORT_ONLY")
        print("CONTROLLER_NEXT_STEP FINAL_REPORT_REVIEW")
        return 0

    if REJECT in out or "SPLIT_GATE False" in out:
        state["last_bc"] = bc
        save_state(state)
        print(f"CONTROLLER_BC{bc} REJECT_OR_GATE_FAIL")
        print("CONTROLLER_NEXT_STEP FAILURE_ANALYSIS_REQUIRED")
        return 0

    print(f"CONTROLLER_DECISION BC{bc}_NO_EXPLICIT_DECISION_BLOCKED")
    return 5

if __name__ == "__main__":
    raise SystemExit(main())
