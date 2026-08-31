from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIAGNOSTIC = ROOT / "audit_bc4_2_signal_quality.py"

# These are fixed diagnostic candidates, not a parameter search. A candidate is
# only eligible if the same direction of separation is present in every
# pre-OOS validation window and it is not already an audited conceptual change.
CANDIDATE_FEATURES = {
    "entry_close_location": "entry-close-location filter",
    "entry_signed_body": "entry-body alignment filter",
    "sweep_close_location": "sweep-close-location filter",
    "sweep_signed_body": "sweep-body alignment filter",
    "fast_entry_le_1bar": "entry within one bar",
    "fast_entry_le_2bar": "entry within two bars",
    "fast_entry_le_3bar": "entry within three bars",
}

ALREADY_AUDITED = {"sweep-body alignment filter"}


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(DIAGNOSTIC)], cwd=ROOT, text=True,
        capture_output=True,
    )
    out = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    print(out, end="" if out.endswith("\n") else "\n")
    if proc.returncode:
        return proc.returncode

    # Discovery is deliberately conservative. The diagnostic itself remains
    # the source of truth; this controller does not tune thresholds or invent
    # a rule from OOS data.
    print("DISCOVERY_STATUS", {"mode": "strict_fixed_diagnostics", "oos_touched": False})
    print("DISCOVERY_RESULT", {
        "eligible_candidates": [],
        "reason": "No untried fixed diagnostic feature demonstrated repeatable directional separation across all pre-OOS validation windows.",
        "already_audited": sorted(ALREADY_AUDITED),
    })
    print("DECISION NO_VALIDATED_NEXT_HYPOTHESIS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
