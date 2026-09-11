#!/usr/bin/env python3
"""Bounded research campaign wrapper.

The campaign policy is static/governing. The agent can propose candidates, but it
cannot increase the budget, alter terminal outcomes, or open OOS.
"""
from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "research" / "campaign_policy.json"
STATE = ROOT / "research" / "bc_lifecycle_state.json"
def load(path, default): return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
def save(state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat(); STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def terminal(state, outcome, reason, screened, budget):
    state["campaign_terminal"] = True; state["campaign_outcome"] = outcome; state["campaign_terminal_reason"] = reason; save(state)
    print(f"CAMPAIGN_TERMINAL outcome={outcome} screened={screened}/{budget}"); return 0
def main():
    policy = load(POLICY, None)
    if not isinstance(policy, dict): print("CAMPAIGN_BLOCKED missing_policy"); return 2
    required = {"campaign_id", "max_screening_candidates", "controller_batch_size", "terminal_outcomes", "promotion_requires"}
    if not required.issubset(policy): print("CAMPAIGN_BLOCKED incomplete_policy"); return 2
    outcomes = set(policy["terminal_outcomes"]); budget = int(policy["max_screening_candidates"]); batch = int(policy["controller_batch_size"])
    if budget <= 0 or batch <= 0 or batch > budget or not outcomes: print("CAMPAIGN_BLOCKED invalid_policy"); return 2
    state = load(STATE, {})
    if state.get("campaign_terminal"):
        outcome = state.get("campaign_outcome")
        if outcome not in outcomes: print(f"CAMPAIGN_BLOCKED persisted_invalid_terminal_outcome={outcome}"); return 3
        print(f"CAMPAIGN_TERMINAL outcome={outcome} screened={state.get('campaign_screened', 0)}/{budget}"); return 0
    screened = int(state.get("campaign_screened", 0))
    if screened >= budget: return terminal(state, "NO_EDGE_FOUND", "FIXED_SCREENING_BUDGET_EXHAUSTED", screened, budget)
    env = dict(os.environ); env["RESEARCH_MAX_ITERATIONS"] = str(min(batch, budget - screened)); before_screened = screened
    print(f"CAMPAIGN_START screened={screened}/{budget} batch={env['RESEARCH_MAX_ITERATIONS']}")
    proc = subprocess.run([sys.executable, "research/bc_controller.py"], cwd=ROOT, env=env)
    if proc.returncode != 0: return proc.returncode
    state = load(STATE, {})
    if state.get("phase") in {"WAIT_RETRY", "HOLD"} or state.get("last_error"):
        state["campaign_budget"] = budget; state["campaign_id"] = policy["campaign_id"]; save(state)
        reason = state.get("last_error") or state.get("phase"); print(f"CAMPAIGN_HOLD reason={reason} screened={before_screened}/{budget}"); return 0
    history = state.get("history", [])
    seen = {int(x["bc"]) for x in history if isinstance(x, dict) and str(x.get("decision")) in {"REJECT", "PROMOTE_TO_FUTURE_OOS_TEST"} and str(x.get("bc", "")).isdigit()}
    screened = max(int(state.get("campaign_screened", 0)), len(seen)); state["campaign_screened"] = screened; state["campaign_budget"] = budget; state["campaign_id"] = policy["campaign_id"]
    if state.get("terminal"):
        raw = state.get("terminal_reason")
        if raw == "OOS_PASS": outcome = "EDGE_FOUND"
        elif raw == "OOS_FAIL": outcome = "NO_EDGE_FOUND"
        else: outcome = "INCONCLUSIVE" if raw in {"HOLD", "UNKNOWN"} else raw
        if outcome not in outcomes: print(f"CAMPAIGN_BLOCKED terminal_reason_not_in_policy={raw}"); save(state); return 3
        state["campaign_terminal"] = True; state["campaign_outcome"] = outcome; state["campaign_terminal_reason"] = raw; save(state)
        print(f"CAMPAIGN_TERMINAL outcome={outcome} screened={screened}/{budget}"); return 0
    if screened >= budget: return terminal(state, "NO_EDGE_FOUND", "FIXED_SCREENING_BUDGET_EXHAUSTED", screened, budget)
    if screened <= before_screened:
        save(state); print(f"CAMPAIGN_HOLD reason=NO_NEW_SCREENED_BC screened={screened}/{budget}"); return 0
    save(state); print(f"CAMPAIGN_CONTINUE screened={screened}/{budget}"); return 0
if __name__ == "__main__": raise SystemExit(main())
