from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'research' / 'campaign_policy.json'
STATE = ROOT / 'research' / 'bc_lifecycle_state.json'
CANDIDATE_DIR = ROOT / 'research' / 'autonomous_candidates'
FAILURE_DIR = ROOT / 'research' / 'failure_analysis'
OOS_DIR = ROOT / 'research' / 'oos'
QUEUE = ROOT / 'research' / 'bc_queue.json'
QUALIFY = {'REJECT', 'PROMOTE_TO_FUTURE_OOS_TEST'}
SCREENED_DECISIONS = QUALIFY | {'REJECT_BC'}


class LifecycleAction(StrEnum):
    TERMINAL = 'TERMINAL'
    BLOCKED = 'BLOCKED'
    CONTINUE_DURABLE_QUEUE = 'CONTINUE_DURABLE_QUEUE'
    CONTINUE_RETRY = 'CONTINUE_RETRY'
    CONTINUE_PROGRESS = 'CONTINUE_PROGRESS'
    HOLD = 'HOLD'
    BUDGET_EXHAUSTED = 'BUDGET_EXHAUSTED'


def lifecycle_transition(*, terminal_state: bool, terminal_outcome_valid: bool,
                         budget_exhausted: bool, durable_queue: bool,
                         retry_allowed: bool, blocked: bool,
                         progress_event: bool) -> LifecycleAction:
    """Single transition contract; accounting counters never decide liveness."""
    if blocked:
        return LifecycleAction.BLOCKED
    if terminal_state:
        return LifecycleAction.TERMINAL if terminal_outcome_valid else LifecycleAction.BLOCKED
    if durable_queue:
        return LifecycleAction.CONTINUE_DURABLE_QUEUE
    if budget_exhausted:
        return LifecycleAction.BUDGET_EXHAUSTED
    if retry_allowed:
        return LifecycleAction.CONTINUE_RETRY
    if progress_event:
        return LifecycleAction.CONTINUE_PROGRESS
    return LifecycleAction.HOLD


def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save(state):
    state['updated_at'] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def terminal(state, outcome, reason, screened, budget):
    state.update(campaign_terminal=True, campaign_outcome=outcome,
                 campaign_terminal_reason=reason, campaign_screened=min(int(screened), int(budget)))
    save(state)
    print(f'CAMPAIGN_TERMINAL outcome={outcome} screened={state["campaign_screened"]}/{budget}')
    return 0


def qualifying_bcs(history, start=1):
    out = set()
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get('bc', '')).strip()
        if raw.isdigit() and int(raw) >= int(start) and str(item.get('decision')) in QUALIFY:
            out.add(int(raw))
    return out


def screened_bcs(history, start=1):
    """Durably evaluated BCs; distinct from qualifying outcomes."""
    out = set()
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get('bc', '')).strip()
        if not raw.isdigit() or int(raw) < int(start):
            continue
        if (str(item.get('decision') or '') in SCREENED_DECISIONS
                or str(item.get('event_type') or '') == 'OOS_EVALUATION'
                or str(item.get('oos_state') or '') == 'OOS_EVALUATED'):
            out.add(int(raw))
    return out


def _epoch_start(state, history):
    if state.get('campaign_epoch_initialized') and isinstance(state.get('campaign_start_bc'), int):
        return int(state['campaign_start_bc'])
    vals = [int(x['bc']) for x in history if isinstance(x, dict) and str(x.get('bc', '')).isdigit() and x.get('next') == 'AGENT_HYPOTHESIS']
    qualifying = qualifying_bcs(history)
    return min(vals) if vals else (min(qualifying) if qualifying else 1)


def _durable_completed_bcs(start=1):
    if not CANDIDATE_DIR.exists() or not FAILURE_DIR.exists():
        return start - 1
    candidates = {int(p.stem[2:]) for p in CANDIDATE_DIR.glob('BC*.json') if p.stem[2:].isdigit()}
    failures = {int(p.stem[2:]) for p in FAILURE_DIR.glob('BC*.json') if p.stem[2:].isdigit()}
    n = start - 1
    while n + 1 in candidates and n + 1 in failures:
        n += 1
    return n


def reconcile_campaign_state(state, budget):
    history = state.get('history', []) if isinstance(state.get('history', []), list) else []
    start = _epoch_start(state, history)
    completed = _durable_completed_bcs(start)
    known = {int(x['bc']) for x in history if isinstance(x, dict) and str(x.get('bc', '')).isdigit() and int(x['bc']) >= start}
    repaired = 0
    for bc in range(start, completed + 1):
        if bc in known:
            continue
        candidate = load(CANDIDATE_DIR / f'BC{bc}.json', {})
        failure = load(FAILURE_DIR / f'BC{bc}.json', {})
        decision = failure.get('decision')
        if decision not in QUALIFY:
            continue
        history.append({'bc': bc, 'decision': decision,
                        'hypothesis_id': candidate.get('hypothesis_id') or failure.get('hypothesis_id'),
                        'candidate_hash': candidate.get('candidate_hash') or failure.get('candidate_hash'),
                        'reason': failure.get('reason')})
        repaired += 1
    state['campaign_start_bc'] = start
    state['history'] = sorted(history, key=lambda x: int(x.get('bc', 0)) if isinstance(x, dict) and str(x.get('bc', '')).isdigit() else 0)
    screened = len(screened_bcs(history, start))
    state['campaign_screened'] = min(screened, int(budget))
    if repaired:
        state['state_reconciled_from_durable_bc_artifacts'] = True
        print(f'CAMPAIGN_RECONCILED repaired_history={repaired} completed_bc={completed} start_bc={start} screened={screened}/{budget}')
    return completed, start, screened


def retry_resume_allowed(state):
    return (not state.get('campaign_terminal') and not state.get('terminal')
            and state.get('phase') == 'WAIT_RETRY'
            and int(state.get('retry_count', 0)) < int(os.environ.get('RESEARCH_MAX_RESUME_RETRIES', '3'))
            and bool(state.get('last_error')))


def continuation_allowed(*, new_screened: int, phase: str | None,
                         last_error: object, terminal_state: bool) -> bool:
    return lifecycle_transition(
        terminal_state=terminal_state,
        terminal_outcome_valid=True,
        budget_exhausted=False,
        durable_queue=False,
        retry_allowed=phase == 'WAIT_RETRY' and bool(last_error),
        blocked=phase == 'HOLD',
        progress_event=new_screened > 0,
    ) is LifecycleAction.CONTINUE_PROGRESS


def _start_new_campaign_epoch(state, policy):
    campaign_id = str(policy['campaign_id'])
    old = str(state.get('campaign_id') or '')
    if old == campaign_id:
        if (state.get('campaign_epoch_initialized') and isinstance(state.get('campaign_start_bc'), int)
                and int(state.get('next_bc') or 0) < int(state['campaign_start_bc'])):
            state['next_bc'] = int(state['campaign_start_bc'])
            save(state)
        return
    history = state.get('history', []) if isinstance(state.get('history', []), list) else []
    bcs = [int(x['bc']) for x in history if isinstance(x, dict) and str(x.get('bc', '')).isdigit()]
    start = max(bcs + [int(state.get('current_bc') or state.get('last_bc') or 0)]) + 1
    state.update(campaign_id=campaign_id, campaign_epoch_initialized=True, campaign_start_bc=start,
                 next_bc=start, campaign_screened=0, campaign_terminal=False, campaign_outcome=None,
                 campaign_terminal_reason=None, phase='OBSERVE', last_error=None, retry_count=0,
                 terminal=False, capabilities=['research'])
    print(f'CAMPAIGN_NEW_EPOCH id={campaign_id} start_bc={start} prior_id={old or "none"}')
    save(state)


def _ensure_research_capability(state, policy):
    if state.get('capabilities') is None:
        state['capabilities'] = ['research']
        state['capability_repaired_from_campaign_policy'] = True
        save(state)
        print('CAMPAIGN_CAPABILITY_REPAIRED research')
    return state


def _migrate_candidate_oos_terminal(state):
    if not (state.get('campaign_terminal') and state.get('campaign_terminal_reason') == 'OOS_FAIL'):
        return False
    raw_parent = state.get('oos_failed_bc')
    if not isinstance(raw_parent, int) or raw_parent <= 0:
        print('CAMPAIGN_MIGRATE_OOS_FAIL_HOLD reason=MISSING_EXPLICIT_OOS_FAILED_BC')
        return False
    parent = raw_parent
    candidate_path = CANDIDATE_DIR / f'BC{parent}.json'
    result_path = OOS_DIR / f'BC{parent}_oos_result.json'
    receipt_path = OOS_DIR / f'BC{parent}_oos_result_receipt.json'
    failure_path = FAILURE_DIR / f'BC{parent}.json'
    candidate = load(candidate_path, {}) if candidate_path.exists() else {}
    result = load(result_path, {}) if result_path.exists() else {}
    receipt = load(receipt_path, {}) if receipt_path.exists() else {}
    candidate_hash = candidate.get('candidate_hash')
    evidence_ok = (
        candidate_hash and result.get('bc') == parent and result.get('candidate_hash') == candidate_hash
        and result.get('oos_executed') is True and result.get('oos_selection_used') is False
        and result.get('oos_passed') is False and receipt.get('receipt_type') == 'OOS_EXECUTION_RECEIPT'
        and receipt.get('schema_version') == 1 and receipt.get('bc') == parent
        and receipt.get('candidate_hash') == candidate_hash and receipt.get('oos_executed') is True
        and receipt.get('oos_selection_used') is False and receipt.get('oos_passed') is False
        and receipt.get('metrics') == result.get('metrics')
        and receipt.get('dataset_sha256') == result.get('dataset', {}).get('sha256')
        and receipt.get('protocol_sha256') == result.get('protocol_sha256')
    )
    if not evidence_ok:
        print(f'CAMPAIGN_MIGRATE_OOS_FAIL_HOLD BC{parent} reason=MISSING_DURABLE_OOS_EVIDENCE')
        return False
    FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    if not failure_path.exists():
        failure_path.write_text(json.dumps({
            'bc': parent, 'parent_bc': int(candidate.get('parent_bc', parent - 1)),
            'decision': 'REJECT', 'reason': 'OOS_FAILED', 'hypothesis_id': candidate.get('hypothesis_id'),
            'candidate_hash': candidate_hash, 'conceptual_change': candidate.get('conceptual_change'),
            'evidence_sources': candidate.get('evidence_sources'), 'validation_summary': result.get('metrics'),
            'oos_verdict': 'OOS_FAIL', 'oos_selection_used': False,
            'action': 'reject candidate and require a distinct next hypothesis',
            'migration': 'legacy campaign-level OOS_FAIL converted from durable OOS receipt; no research evidence fabricated'
        }, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    state.update(campaign_terminal=False, campaign_outcome=None,
                 campaign_terminal_reason=None, terminal=False,
                 phase='OBSERVE', last_error=None, retry_count=0,
                 last_oos_migration={'failed_bc': parent, 'reason': 'OOS_FAIL',
                                     'action': 'CANDIDATE_REJECTION'})
    if not isinstance(state.get('next_bc'), int) or state['next_bc'] <= parent:
        state['next_bc'] = parent + 1
    save(state)
    print(f'CAMPAIGN_MIGRATE_OOS_FAIL_RESUME next_bc={state["next_bc"]} failure_analysis=BC{parent}.json')
    return True


def _epoch_seed_failure(parent, start):
    path = FAILURE_DIR / f'BC{parent}.json'
    if path.exists() or parent != start - 1:
        return None
    FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    marker = ROOT / 'research' / '.epoch_seed_failure.json'
    marker.write_text(json.dumps({
        'kind': 'epoch_seed_failure', 'decision': 'SEED_EPOCH', 'parent_bc': parent,
        'epoch_start_bc': start, 'research_evidence': False, 'repair_context': True,
        'reason': 'Epoch seed only; no prior failure evidence. This artifact is bootstrap/repair context, not research evidence.'
    }) + '\n', encoding='utf-8')
    return marker


def controller_command():
    return [sys.executable, '-m', 'research.bc_controller']


def durable_queued_candidate(state, start):
    queue = load(QUEUE, [])
    if not isinstance(queue, list) or not queue:
        return None
    expected = int(state.get('next_bc', start))
    for item in queue:
        if not isinstance(item, dict) or not str(item.get('bc', '')).isdigit():
            continue
        if int(item['bc']) != expected or int(item.get('parent_bc', expected - 1)) != expected - 1:
            continue
        candidate_hash = item.get('candidate_hash')
        if not candidate_hash or not (CANDIDATE_DIR / f'BC{expected}.json').exists():
            continue
        print(f'CAMPAIGN_DURABLE_QUEUE_PRIORITY BC{expected} screened_gate_bypassed=true candidate_hash={candidate_hash}')
        return item
    return None


def main():
    policy = load(POLICY, None)
    if not isinstance(policy, dict):
        print('CAMPAIGN_BLOCKED missing_policy'); return 2
    required = {'campaign_id', 'max_screening_candidates', 'controller_batch_size', 'terminal_outcomes', 'promotion_requires'}
    if not required.issubset(policy):
        print('CAMPAIGN_BLOCKED incomplete_policy'); return 2
    budget = int(policy['max_screening_candidates'])
    batch = int(policy['controller_batch_size'])
    outcomes = set(policy['terminal_outcomes'])
    if budget <= 0 or batch <= 0 or batch > budget or not outcomes:
        print('CAMPAIGN_BLOCKED invalid_policy'); return 2
    state = load(STATE, {})
    _start_new_campaign_epoch(state, policy)
    _ensure_research_capability(state, policy)
    _migrate_candidate_oos_terminal(state)
    _, start, screened = reconcile_campaign_state(state, budget)
    # A full epoch must not erase a durable frontier or a provider retry.
    # Queue/retry obligations have precedence over epoch rollover; only a clean
    # exhausted epoch may advance its boundary.
    queued = durable_queued_candidate(state, start)
    retry_pending = state.get('phase') == 'WAIT_RETRY' and bool(state.get('last_error'))
    if screened >= budget and not state.get('campaign_terminal') and queued is None and not retry_pending:
        next_bc = int(state.get('next_bc') or (start + screened))
        state.update(campaign_epoch=int(state.get('campaign_epoch') or 1) + 1,
                     campaign_start_bc=next_bc, campaign_screened=0,
                     campaign_terminal=False, campaign_outcome=None,
                     campaign_terminal_reason=None, phase='OBSERVE',
                     last_error=None, retry_count=0, terminal=False)
        save(state)
        start, screened = next_bc, 0
        print(f'CAMPAIGN_NEW_EPOCH id={state["campaign_id"]} epoch={state["campaign_epoch"]} start_bc={start}')
    queued = durable_queued_candidate(state, start)
    if state.get('campaign_terminal') and queued is None:
        outcome = state.get('campaign_outcome')
        if outcome not in outcomes:
            print(f'CAMPAIGN_BLOCKED persisted_invalid_terminal_outcome={outcome}'); return 3
        print(f'CAMPAIGN_TERMINAL outcome={outcome} screened={state.get("campaign_screened", 0)}/{budget}')
        return 0
    if queued is None and screened >= budget:
        return terminal(state, 'NO_EDGE_FOUND', 'FIXED_SCREENING_BUDGET_EXHAUSTED', screened, budget)
    env = dict(os.environ)
    env['RESEARCH_MAX_ITERATIONS'] = str(1 if queued else min(batch, budget - screened))
    before = screened_bcs(state.get('history', []), start)
    expected = int(state.get('next_bc', start))
    seed = None if queued else _epoch_seed_failure(expected - 1, start)
    if seed is not None:
        env['RESEARCH_EPOCH_SEED_FAILURE'] = str(seed)
    print(f'CAMPAIGN_START screened={screened}/{budget} batch={env["RESEARCH_MAX_ITERATIONS"]} start_bc={start} queued={bool(queued)}')
    try:
        rc = subprocess.run(controller_command(), cwd=ROOT, env=env).returncode
    finally:
        if seed is not None and seed.exists():
            seed.unlink()
    if rc:
        return rc
    state = load(STATE, {})
    _, start, after = reconcile_campaign_state(state, budget)
    queued_after = durable_queued_candidate(state, start)
    if queued_after is not None and not state.get('terminal'):
        action = lifecycle_transition(terminal_state=False, terminal_outcome_valid=True,
                                      budget_exhausted=False, durable_queue=True,
                                      retry_allowed=False, blocked=False, progress_event=False)
        if action is not LifecycleAction.CONTINUE_DURABLE_QUEUE:
            return 4
        state.update(campaign_budget=budget, campaign_id=policy['campaign_id'],
                     campaign_terminal=False, campaign_outcome=None, phase='PERSISTED',
                     last_error=None, retry_count=0)
        save(state)
        print(f'CAMPAIGN_CONTINUE_DURABLE_QUEUE BC{queued_after["bc"]} screened={after}/{budget}')
        return 0
    retry_allowed = retry_resume_allowed(state)
    blocked = state.get('phase') == 'HOLD'
    if state.get('phase') in {'WAIT_RETRY', 'HOLD'} or state.get('last_error'):
        action = lifecycle_transition(
            terminal_state=False, terminal_outcome_valid=True,
            budget_exhausted=False, durable_queue=False,
            retry_allowed=retry_allowed, blocked=blocked,
            progress_event=False,
        )
        state['campaign_budget'] = budget
        state['campaign_id'] = policy['campaign_id']
        save(state)
        reason = state.get('last_error') or state.get('phase')
        if action is LifecycleAction.CONTINUE_RETRY:
            print(f'CAMPAIGN_CONTINUE_RETRY retry={state.get("retry_count", 0)}/{os.environ.get("RESEARCH_MAX_RESUME_RETRIES", "3")} reason={reason} screened={after}/{budget}')
        else:
            print(f'CAMPAIGN_HOLD reason={reason} screened={after}/{budget}')
        return 0
    history = state.get('history', [])
    after_set = screened_bcs(history, start)
    new = after_set - before
    state.update(campaign_screened=min(after, budget), campaign_budget=budget, campaign_id=policy['campaign_id'])
    if state.get('terminal'):
        raw = state.get('terminal_reason')
        outcome = ('EDGE_FOUND' if raw == 'OOS_PASS' else 'NO_EDGE_FOUND' if raw == 'OOS_FAIL'
                   else 'INCONCLUSIVE' if raw in {'HOLD', 'UNKNOWN'} else raw)
        action = lifecycle_transition(terminal_state=True, terminal_outcome_valid=outcome in outcomes,
                                      budget_exhausted=False, durable_queue=False,
                                      retry_allowed=False, blocked=False, progress_event=False)
        if action is LifecycleAction.BLOCKED:
            print(f'CAMPAIGN_BLOCKED terminal_reason_not_in_policy={raw}'); save(state); return 3
        if raw == 'OOS_FAIL':
            failed_bc = state.get('current_bc')
            if not isinstance(failed_bc, int) or failed_bc <= 0:
                print('CAMPAIGN_BLOCKED OOS_FAIL_MISSING_CURRENT_BC')
                save(state)
                return 3
            state['oos_failed_bc'] = failed_bc
        state.update(campaign_terminal=True, campaign_outcome=outcome, campaign_terminal_reason=raw)
        save(state)
        print(f'CAMPAIGN_TERMINAL outcome={outcome} screened={after}/{budget}')
        return 0
    action = lifecycle_transition(terminal_state=False, terminal_outcome_valid=True,
                                  budget_exhausted=after >= budget, durable_queue=False,
                                  retry_allowed=False, blocked=False, progress_event=bool(new))
    if action is LifecycleAction.BUDGET_EXHAUSTED:
        return terminal(state, 'NO_EDGE_FOUND', 'FIXED_SCREENING_BUDGET_EXHAUSTED', after, budget)
    if action is LifecycleAction.HOLD:
        # Accounting stasis is not a research verdict. The next invocation must
        # continue the durable frontier; only explicit controller/provider states
        # may produce HOLD.
        state['campaign_frontier_transition_required'] = True
        save(state)
        print(f'CAMPAIGN_CONTINUE reason=FRONTIER_NO_NEW_SCREENED_BC screened={after}/{budget}')
        return 0
    save(state)
    print(f'CAMPAIGN_CONTINUE screened={after}/{budget}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
