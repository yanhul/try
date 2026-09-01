#!/usr/bin/env python3
"""Register the existing baseline as BC1 without inventing research results."""
from __future__ import annotations
import json
from pathlib import Path
from autonomous_hypothesis import load_candidate, write_candidate

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "research" / "autonomous_candidates" / "BC1.json"
OUT = ROOT / "research" / "autonomous_candidates" / "BC1.json"
QUEUE = ROOT / "research" / "bc_queue.json"
FAILURE = ROOT / "research" / "failure_analysis" / "BC1.json"

candidate = load_candidate(SRC, 1, 0)
write_candidate(OUT, candidate)
queue = []
if QUEUE.exists():
    value = json.loads(QUEUE.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise SystemExit("bc_queue.json must be a list")
    queue = value
if not any(x.get("candidate_hash") == candidate["candidate_hash"] for x in queue):
    queue.append(candidate)
    QUEUE.write_text(json.dumps(queue, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"BOOTSTRAP_REGISTERED BC1 hash={candidate['candidate_hash']} failure_analysis={FAILURE}")
