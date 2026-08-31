from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAST_GATE = re.compile(r"audit_bc(\d+)_fast_gate\.py$")
PROMOTE = "PROMOTE_TO_FUTURE_OOS_TEST"
REJECT = "REJECT_BC"


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    out = p.stdout + p.stderr
    print(out, end="")
    return p.returncode, out


def main() -> int:
    print("BC_CONTROLLER_START strict=1 oos_selection=0")
    rc, _ = run([sys.executable, "-m", "pytest"])
    if rc:
        print("CONTROLLER_DECISION BLOCKED_TEST_FAILURE")
        return rc

    gates = sorted(
        ROOT.glob("audit_bc*_fast_gate.py"),
        key=lambda p: int(FAST_GATE.match(p.name).group(1)) if FAST_GATE.match(p.name) else 10**9,
    )
    if not gates:
        print("CONTROLLER_DECISION NO_CANDIDATE_GATES")
        return 0

    for gate in gates:
        m = FAST_GATE.match(gate.name)
        if not m:
            continue
        bc = int(m.group(1))
        print(f"CONTROLLER_BC {bc} GATE {gate.name}")
        rc, out = run([sys.executable, gate.name])
        if rc:
            print(f"CONTROLLER_DECISION BC{bc}_SCRIPT_FAILURE")
            return rc
        if PROMOTE in out:
            oos = ROOT / f"audit_bc{bc}_future_oos.py"
            if not oos.exists():
                print(f"CONTROLLER_DECISION BC{bc}_PROMOTED_BUT_NO_FROZEN_OOS_AUDIT")
                return 3
            print(f"CONTROLLER_BC{bc}_OOS START frozen=1 selection=0")
            rc, oos_out = run([sys.executable, oos.name])
            if rc:
                print(f"CONTROLLER_DECISION BC{bc}_OOS_SCRIPT_FAILURE")
                return rc
            if "SELECTION" in oos_out and "NO" not in oos_out:
                print("CONTROLLER_DECISION BLOCKED_OOS_SELECTION_DETECTED")
                return 4
            print(f"CONTROLLER_BC{bc}_OOS REPORT_ONLY")
        elif REJECT in out or "SPLIT_GATE False" in out:
            print(f"CONTROLLER_BC{bc} REJECT_OR_GATE_FAIL continue=1")
        else:
            print(f"CONTROLLER_BC{bc} NO_EXPLICIT_DECISION_BLOCKED")
            return 5

    print("CONTROLLER_DECISION COMPLETE_NO_SELECTION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
