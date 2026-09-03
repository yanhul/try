"""Fail-closed terminal transition gate.

The BC controller may propose a terminal transition, but this gate requires an
externally issued AIOS contract/permit and matching terminal state. It never
issues authority and cannot change promotion criteria.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from aios_authority import verify_external_authority


def authorize_terminal(state: dict, authority_dir: str | Path) -> dict:
    if not isinstance(state, dict):
        raise ValueError("state must be an object")
    if state.get("terminal") is not True:
        raise ValueError("terminal transition not requested")
    contract_id = str(state.get("authority_contract_id") or "")
    permit_id = str(state.get("authority_permit_id") or "")
    if not contract_id or not permit_id:
        raise ValueError("terminal transition lacks external AIOS authority")
    contract = verify_external_authority(authority_dir, contract_id, permit_id)
    if "terminal" not in contract.get("terminal_states", []):
        raise ValueError("contract does not authorize terminal state")
    return contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--authority-dir", required=True)
    args = parser.parse_args()
    try:
        state = json.loads(Path(args.state).read_text(encoding="utf-8"))
        authorize_terminal(state, args.authority_dir)
    except Exception as exc:
        print(f"AIOS_TERMINAL_AUTHORITY: BLOCKED: {exc}")
        return 1
    print("AIOS_TERMINAL_AUTHORITY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
