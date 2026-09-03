#!/usr/bin/env python3
"""Bounded research campaign wrapper.

The campaign policy is static/governing. The agent can propose candidates, but it
cannot increase the budget, alter terminal outcomes, or open OOS.
"""
from __future__ import annotations
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "research" / "campaign_policy.json"
STATE = ROOT / "research" / "bc_lifecycle_state.json"


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    policy = load(POLICY, None)
    if not isinstance(policy, dict):
        print("CAMPAIGN_BLOCKED missing_policy")
        return 2
    required = {"max_screening_candidates", "controller_batch_size", "terminal_outcomes", "promotion_requires"}
    if not required.issubset(policy):
        print("CAMPAIGN_BLOCKED incomplete_policy")
        return 2
    budget = int(policy["max_screening_candidates"])
    batch = int(policy["controller_batch_size"])
    if budget <= 0 or batch <= 0 or batch > budget:
        print("CAMPAIGN_BLOCKED invalid_policy")
        return 2

    state = load(STATE, {})
    if state.get("campaign_terminal"):
        print(f"CAMPAIGN_TERMINAL outcome={state.get('campaign_outcome')} screened={state.get('campaign_screened', 0)}/{budget}")
        return 0

    screened = int(state.get("campaign_screened", 0))
    if screened >= budget:
        state["campaign_terminal"] = True
        state["campaign_outcome"] = "NO_EDGE_FOUND"
        state["campaign_terminal_reason"] = "FIXED_SCREENING_BUDGET_EXHAUSTED"
        save(state)
        print(f"CAMPAIGN_TERMINAL outcome=NO_EDGE_FOUND screened={screened}/{budget}")
        return 0

    env = dict(__import__("os").environ)
    env["RESEARCH_MAX_ITERATIONS"] = str(min(batch, budget - screened))
    print(f"CAMPAIGN_START screened={screened}/{budget} batch={env['RESEARCH_MAX_ITERATIONS']}")
    proc = subprocess.run([sys.executable, "research/bc_controller.py"], cwd=ROOT, env=env, text=True)
    if proc.returncode != 0:
        return proc.returncode

    state = load(STATE, {})
    history = state.get("history", [])
    # Count unique screened BCs, not controller loop iterations.
    seen = {int(x["bc"]) for x in history if isinstance(x, dict) and str(x.get("decision")) in {"REJECT", "PROMOTE_TO_FUTURE_OOS_TEST"} and str(x.get("bc", "")).isdigit()}
    screened = max(int(state.get("campaign_screened", 0)), len(seen))
    state["campaign_screened"] = screened
    state["campaign_budget"] = budget
    state["campaign_id"] = policy["campaign_id"]

    if state.get("terminal"):
        state["campaign_terminal"] = True
        state["campaign_outcome"] = state.get("terminal_reason", "EDGE_FOUND")
        save(state)
        print(f"CAMPAIGN_TERMINAL outcome={state['campaign_outcome']} screened={screened}/{budget}")
        return 0

    if screened >= budget:
        state["campaign_terminal"] = True
        state["campaign_outcome"] = "NO_EDGE_FOUND"
        state["campaign_terminal_reason"] = "FIXED_SCREENING_BUDGET_EXHAUSTED"
        save(state)
        print(f"CAMPAIGN_TERMINAL outcome=NO_EDGE_FOUND screened={screened}/{budget}")
        return 0

    save(state)
    print(f"CAMPAIGN_CONTINUE screened={screened}/{budget}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
