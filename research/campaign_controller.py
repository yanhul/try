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
CANDIDATE_DIR = ROOT / "research" / "autonomous_candidates"
FAILURE_DIR = ROOT / "research" / "failure_analysis"


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def terminal(state, outcome, reason, screened, budget):
    state["campaign_terminal"] = True
    state["campaign_outcome"] = outcome
    state["campaign_terminal_reason"] = reason
    state["campaign_screened"] = min(int(screened), int(budget))
    save(state)
    print(f"CAMPAIGN_TERMINAL outcome={outcome} screened={state['campaign_screened']}/{budget}")
    return 0


def qualifying_bcs(history):
    """Return BC ids that count as screened, preserving the governing policy."""
    return {int(x["bc"]) for x in history if isinstance(x, dict) and str(x.get("decision")) in {"REJECT", "PROMOTE_TO_FUTURE_OOS_TEST"} and str(x.get("bc", "")).isdigit()}


def _durable_completed_bcs():
    """Return contiguous BCs with both immutable candidate and failure artifacts."""
    if not CANDIDATE_DIR.exists() or not FAILURE_DIR.exists():
        return 0
    candidates = {int(p.stem[2:]) for p in CANDIDATE_DIR.glob("BC*.json") if p.stem[2:].isdigit()}
    failures = {int(p.stem[2:]) for p in FAILURE_DIR.glob("BC*.json") if p.stem[2:].isdigit()}
    completed = 0
    while completed + 1 in candidates and completed + 1 in failures:
        completed += 1
    return completed


def reconcile_campaign_state(state, budget):
    """Rebuild missing history and screen accounting from durable BC artifacts.

    The previous implementation trusted a stale history counter. That allowed
    repeated scheduler resumes to generate BCs beyond the fixed campaign budget
    when durable candidate/failure artifacts were ahead of the history list.
    """
    history = state.get("history", [])
    if not isinstance(history, list):
        history = []
    known = {int(x.get("bc", -1)) for x in history if isinstance(x, dict) and str(x.get("bc", "")).isdigit()}
    completed = _durable_completed_bcs()
    repaired = 0
    for bc in range(1, completed + 1):
        if bc in known:
            continue
        candidate = load(CANDIDATE_DIR / f"BC{bc}.json", {})
        failure = load(FAILURE_DIR / f"BC{bc}.json", {})
        decision = failure.get("decision")
        if decision == "PROMOTE_TO_FUTURE_OOS_TEST":
            normalized = decision
        elif decision == "REJECT":
            normalized = "REJECT"
        else:
            # A durable artifact without an admissible terminal screening decision
            # must not be counted as screened.
            continue
        history.append({
            "bc": bc,
            "decision": normalized,
            "hypothesis_id": candidate.get("hypothesis_id") or failure.get("hypothesis_id"),
            "candidate_hash": candidate.get("candidate_hash") or failure.get("candidate_hash"),
            "reason": failure.get("reason"),
        })
        repaired += 1
        known.add(bc)

    # This campaign inherited legacy BCs. BC31 is the first autonomous screening
    # entry (the history records `next=AGENT_HYPOTHESIS` there), so infer that
    # boundary from durable history rather than hard-coding it.
    starts = [
        int(x["bc"]) for x in history
        if isinstance(x, dict)
        and str(x.get("bc", "")).isdigit()
        and x.get("next") == "AGENT_HYPOTHESIS"
    ]
    if not starts:
        # Fresh campaigns have no legacy history; their first qualifying BC is 1.
        qualifying = qualifying_bcs(history)
        start = min(qualifying) if qualifying else 1
    else:
        start = min(starts)
    campaign_bcs = qualifying_bcs(history)
    screened = len({bc for bc in campaign_bcs if bc >= start})
    state["campaign_start_bc"] = start
    state["history"] = sorted(history, key=lambda x: int(x.get("bc", 0)) if str(x.get("bc", "")).isdigit() else 0)
    state["campaign_screened"] = min(screened, budget)
    if repaired:
        state["state_reconciled_from_durable_bc_artifacts"] = True
        print(f"CAMPAIGN_RECONCILED repaired_history={repaired} completed_bc={completed} start_bc={start} screened={screened}/{budget}")
    return completed, start, screened


def retry_resume_allowed(state):
    """Allow bounded wake-up for retryable controller holds only."""
    if state.get("campaign_terminal") or state.get("terminal"):
        return False
    if state.get("phase") != "WAIT_RETRY":
        return False
    retry_count = int(state.get("retry_count", 0))
    max_retries = int(os.environ.get("RESEARCH_MAX_RESUME_RETRIES", "3"))
    return retry_count < max_retries and bool(state.get("last_error"))


def continuation_allowed(*, new_screened: int, phase: str | None, last_error: object, terminal_state: bool) -> bool:
    """Authorize normal wake-up only when this invocation produced new screened BCs."""
    if terminal_state or phase in {"WAIT_RETRY", "HOLD"} or last_error:
        return False
    return new_screened > 0


def main():
    policy = load(POLICY, None)
    if not isinstance(policy, dict):
        print("CAMPAIGN_BLOCKED missing_policy")
        return 2
    required = {"campaign_id", "max_screening_candidates", "controller_batch_size", "terminal_outcomes", "promotion_requires"}
    if not required.issubset(policy):
        print("CAMPAIGN_BLOCKED incomplete_policy")
        return 2
    outcomes = set(policy["terminal_outcomes"])
    budget = int(policy["max_screening_candidates"])
    batch = int(policy["controller_batch_size"])
    if budget <= 0 or batch <= 0 or batch > budget or not outcomes:
        print("CAMPAIGN_BLOCKED invalid_policy")
        return 2
    state = load(STATE, {})
    completed, campaign_start, reconciled_screened = reconcile_campaign_state(state, budget)

    if state.get("campaign_terminal"):
        outcome = state.get("campaign_outcome")
        if outcome not in outcomes:
            print(f"CAMPAIGN_BLOCKED persisted_invalid_terminal_outcome={outcome}")
            return 3
        print(f"CAMPAIGN_TERMINAL outcome={outcome} screened={state.get('campaign_screened', 0)}/{budget}")
        return 0

    # The governing budget is over autonomous screening candidates, not raw BC
    # numbers. Once the durable record reaches the budget, no new BC may be made.
    if reconciled_screened >= budget:
        window = {bc: x for x in state.get("history", []) if isinstance(x, dict) and str(x.get("bc", "")).isdigit() for bc in [int(x["bc"])] if campaign_start <= bc < campaign_start + budget}
        promotions = [x for x in window.values() if x.get("decision") == "PROMOTE_TO_FUTURE_OOS_TEST"]
        if promotions:
            # A promotion should already have taken the controller terminal path;
            # refusing to reinterpret it as NO_EDGE_FOUND preserves the gate.
            print("CAMPAIGN_BLOCKED budget_exhausted_with_unconsumed_promotion")
            save(state)
            return 3
        return terminal(state, "NO_EDGE_FOUND", "FIXED_SCREENING_BUDGET_EXHAUSTED", budget, budget)

    screened = reconciled_screened
    env = dict(os.environ)
    env["RESEARCH_MAX_ITERATIONS"] = str(min(batch, budget - screened))
    before_screened = screened
    before_history = list(state.get("history", []))
    before_bcs = qualifying_bcs(before_history)
    print(f"CAMPAIGN_START screened={screened}/{budget} batch={env['RESEARCH_MAX_ITERATIONS']}")
    proc = subprocess.run([sys.executable, "research/bc_controller.py"], cwd=ROOT, env=env)
    if proc.returncode != 0:
        return proc.returncode
    state = load(STATE, {})
    _, campaign_start, after_reconciled = reconcile_campaign_state(state, budget)
    if state.get("phase") in {"WAIT_RETRY", "HOLD"} or state.get("last_error"):
        state["campaign_budget"] = budget
        state["campaign_id"] = policy["campaign_id"]
        save(state)
        reason = state.get("last_error") or state.get("phase")
        if retry_resume_allowed(state):
            retry_count = int(state.get("retry_count", 0))
            max_retries = int(os.environ.get("RESEARCH_MAX_RESUME_RETRIES", "3"))
            print(f"CAMPAIGN_CONTINUE_RETRY retry={retry_count}/{max_retries} reason={reason} screened={before_screened}/{budget}")
        else:
            print(f"CAMPAIGN_HOLD reason={reason} screened={before_screened}/{budget}")
        return 0
    history = state.get("history", [])
    after_bcs = qualifying_bcs(history)
    new_bcs = after_bcs - before_bcs
    screened = after_reconciled
    state["campaign_screened"] = min(budget, screened)
    state["campaign_budget"] = budget
    state["campaign_id"] = policy["campaign_id"]
    if state.get("terminal"):
        raw = state.get("terminal_reason")
        if raw == "OOS_PASS":
            outcome = "EDGE_FOUND"
        elif raw == "OOS_FAIL":
            outcome = "NO_EDGE_FOUND"
        else:
            outcome = "INCONCLUSIVE" if raw in {"HOLD", "UNKNOWN"} else raw
        if outcome not in outcomes:
            print(f"CAMPAIGN_BLOCKED terminal_reason_not_in_policy={raw}")
            save(state)
            return 3
        state["campaign_terminal"] = True
        state["campaign_outcome"] = outcome
        state["campaign_terminal_reason"] = raw
        save(state)
        print(f"CAMPAIGN_TERMINAL outcome={outcome} screened={screened}/{budget}")
        return 0
    if screened >= budget:
        return terminal(state, "NO_EDGE_FOUND", "FIXED_SCREENING_BUDGET_EXHAUSTED", screened, budget)
    if not continuation_allowed(new_screened=len(new_bcs), phase=state.get("phase"), last_error=state.get("last_error"), terminal_state=bool(state.get("terminal"))):
        save(state)
        print(f"CAMPAIGN_HOLD reason=NO_NEW_SCREENED_BC screened={screened}/{budget}")
        return 0
    save(state)
    print(f"CAMPAIGN_CONTINUE screened={screened}/{budget}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
