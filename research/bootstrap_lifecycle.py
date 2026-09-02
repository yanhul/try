#!/usr/bin/env python3
"""Bootstrap/reconcile durable research state without discarding completed BC history."""
from __future__ import annotations
import json
import re
from pathlib import Path

from autonomous_hypothesis import load_candidate, write_candidate

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "research" / "autonomous_candidates" / "BC1.json"
QUEUE = ROOT / "research" / "bc_queue.json"
STATE = ROOT / "research" / "bc_lifecycle_state.json"
FAILURE_DIR = ROOT / "research" / "failure_analysis"
CANDIDATE_DIR = ROOT / "research" / "autonomous_candidates"


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def bc_numbers(directory: Path) -> set[int]:
    if not directory.exists():
        return set()
    out: set[int] = set()
    for path in directory.glob("BC*.json"):
        m = re.fullmatch(r"BC(\d+)\.json", path.name)
        if m:
            out.add(int(m.group(1)))
    return out


state = load_json(STATE, {})
candidates = bc_numbers(CANDIDATE_DIR)
failures = bc_numbers(FAILURE_DIR)

# Recover a stale checkpoint from durable candidate/failure lineage.
completed = 0
while completed + 1 in candidates and completed + 1 in failures:
    completed += 1

if completed >= 1:
    persisted_next = int(state.get("next_bc", 1))
    persisted_last = int(state.get("last_bc", 0))
    if persisted_next <= completed or persisted_last < completed:
        history = state.get("history", [])
        if not isinstance(history, list):
            history = []
        known = {int(x.get("bc", -1)) for x in history if isinstance(x, dict)}
        for bc in range(1, completed + 1):
            if bc in known:
                continue
            f = load_json(FAILURE_DIR / f"BC{bc}.json", {})
            c = load_json(CANDIDATE_DIR / f"BC{bc}.json", {})
            history.append({
                "bc": bc,
                "decision": "REJECT" if f.get("decision") == "REJECT" else f.get("decision", "COMPLETED"),
                "hypothesis_id": c.get("hypothesis_id") or f.get("hypothesis_id"),
                "candidate_hash": c.get("candidate_hash"),
                "reason": f.get("reason"),
            })
        state.update({
            "history": history,
            "last_bc": completed,
            "next_bc": completed + 1,
            "current_bc": completed + 1,
            "phase": "OBSERVE",
            "terminal": False,
            "terminal_reason": None,
            "last_error": None,
            "retry_count": 0,
            "state_reset_reason": "reconciled durable state from contiguous candidate/failure lineage",
        })
        STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"BOOTSTRAP_RECONCILED last_bc={completed} next_bc={completed + 1}")

# Only a genuinely fresh repo registers BC1.
if not STATE.exists() or not candidates:
    candidate = load_candidate(SRC, 1, 0)
    write_candidate(SRC, candidate)
    queue = load_json(QUEUE, [])
    if not isinstance(queue, list):
        raise SystemExit("bc_queue.json must be a list")
    queue = [x for x in queue if isinstance(x, dict) and int(x.get("bc", -1)) == 1]
    if not any(x.get("candidate_hash") == candidate["candidate_hash"] for x in queue):
        queue.append(candidate)
    QUEUE.write_text(json.dumps(queue, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"BOOTSTRAP_REGISTERED BC1 hash={candidate['candidate_hash']}")
else:
    print(f"BOOTSTRAP_PRESERVE_LIFECYCLE last_bc={state.get('last_bc')} next_bc={state.get('next_bc')}")
