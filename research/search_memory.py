"""Durable adaptive search memory for autonomous research.

The evaluator remains authoritative: this module only changes *where the next
candidate is searched*. Strategy failures are learning signals; provider,
authority, receipt, and execution failures must never be recorded as strategy
failures.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = ROOT / "research" / "search_memory.json"
DURABLE_MEMORY_PATH = ROOT / "research" / "discovery" / ".search_memory.json"
FAILURE_DECISIONS = {"FAIL", "REJECT", "OOS_FAIL", "VALIDATION_FAIL"}
PASS_DECISIONS = {"PASS", "PROMOTE", "OOS_PASS", "VALIDATION_PASS"}
STRATEGY_DECISIONS = FAILURE_DECISIONS | PASS_DECISIONS


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def structural_key(candidate):
    spec = candidate.get("discovery_spec") or {}
    return "|".join("" if spec.get(key) is None else str(spec.get(key)) for key in ("mechanism_family", "operator", "left", "right", "direction"))


def _family(candidate):
    return (candidate.get("discovery_spec") or {}).get("mechanism_family") or "discovered_primitive"


def _score(result):
    metrics = result.get("metrics") or result.get("VALIDATION", {}).get("metrics", {})
    pf = _finite(metrics.get("profit_factor")); ret = _finite(metrics.get("total_return")); dd = _finite(metrics.get("max_drawdown")); trades = _finite(metrics.get("trades")) or _finite(metrics.get("trade_count")) or 0.0
    pf = max(0.0, min(3.0, pf if pf is not None else 0.0)); ret = max(-1.0, min(2.0, ret if ret is not None else -1.0)); dd = max(0.0, min(1.0, abs(dd) if dd is not None else 1.0)); activity = min(1.0, trades / 50.0)
    return round(0.45 * pf / 3 + 0.30 * (ret + 1) / 3 + 0.15 * (1 - dd) + 0.10 * activity, 8)


def _default():
    return {"schema_version": 1, "candidates": {}, "families": {}, "events": [], "failures": 0, "regime": "NORMAL", "regime_epoch": 0}


def _read(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1: raise ValueError("invalid_search_memory")
    data.setdefault("candidates", {}); data.setdefault("families", {}); data.setdefault("events", []); data.setdefault("failures", 0); data.setdefault("regime", "NORMAL"); data.setdefault("regime_epoch", 0)
    return data


def load():
    path = MEMORY_PATH if MEMORY_PATH.exists() else DURABLE_MEMORY_PATH
    if not path.exists(): return _default()
    try: return _read(path)
    except Exception as exc: raise RuntimeError(f"search_memory_corrupt:{exc}") from exc


def _event_id(candidate, result, decision):
    payload = {"candidate_hash": candidate.get("candidate_hash"), "bc": candidate.get("bc"), "decision": decision, "result": result}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def record(candidate, result, decision):
    """Record only an actual strategy evaluation, idempotently."""
    if decision not in STRATEGY_DECISIONS: return None
    data = load(); event_id = _event_id(candidate, result, decision)
    if any(event.get("event_id") == event_id for event in data.get("events", [])): return data["candidates"].get(structural_key(candidate))
    key = structural_key(candidate); family = _family(candidate)
    entry = {"event_id": event_id, "bc": candidate.get("bc"), "parent_bc": candidate.get("parent_bc"), "candidate_hash": candidate.get("candidate_hash"), "decision": decision, "score": _score(result), "hypothesis_id": candidate.get("hypothesis_id"), "family": family}
    data["events"].append(entry); data["candidates"][key] = entry; _reaggregate(data); _atomic(data); return entry


def _reaggregate(data):
    families = {}; failures = 0; events = [event for event in data.get("events", []) if event.get("decision") in STRATEGY_DECISIONS]
    for event in events:
        family = event.get("family") or "discovered_primitive"; stats = families.setdefault(family, {"tested": 0, "pass": 0, "fail": 0, "score_sum": 0.0, "recent_failures": 0}); stats["tested"] += 1; decision = event.get("decision")
        if decision in PASS_DECISIONS: stats["pass"] += 1
        elif decision in FAILURE_DECISIONS: stats["fail"] += 1; failures += 1
        stats["score_sum"] += float(event.get("score", 0.0))
    recent_failures_by_family = {}
    for event in events[-8:]:
        if event.get("decision") in FAILURE_DECISIONS:
            family = event.get("family") or "discovered_primitive"; recent_failures_by_family[family] = recent_failures_by_family.get(family, 0) + 1
    for family, count in recent_failures_by_family.items(): families.setdefault(family, {"tested": 0, "pass": 0, "fail": 0, "score_sum": 0.0, "recent_failures": 0})["recent_failures"] = count
    data["families"] = families; data["failures"] = failures; data["regime"] = "STAGNANT" if stagnant(data, 8) else "NORMAL"


def _atomic(data):
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    for target in (MEMORY_PATH, DURABLE_MEMORY_PATH):
        target.parent.mkdir(parents=True, exist_ok=True); tmp = target.with_suffix(target.suffix + ".tmp"); tmp.write_text(payload, encoding="utf-8"); os.replace(tmp, target)


def rebuild_from_artifacts(data=None):
    """Reconcile durable OOS/validation outcomes into the next-search memory."""
    data = data or load(); canddir = ROOT / "research" / "autonomous_candidates"; faildir = ROOT / "research" / "failure_analysis"; oosdir = ROOT / "research" / "oos"
    if not canddir.exists(): _reaggregate(data); _atomic(data); return data
    for path in sorted(canddir.glob("BC*.json")):
        try: candidate = json.loads(path.read_text(encoding="utf-8")); bc = int(candidate["bc"])
        except Exception: continue
        decision = None; result = {}
        fp = faildir / f"BC{bc}.json"
        if fp.exists():
            try:
                failure = json.loads(fp.read_text(encoding="utf-8"));
                if failure.get("oos_verdict") == "OOS_FAIL": decision, result = "OOS_FAIL", failure
            except Exception: pass
        op = oosdir / f"BC{bc}_oos_result.json"
        if op.exists():
            try:
                oos = json.loads(op.read_text(encoding="utf-8")); decision, result = (("OOS_PASS", oos) if oos.get("oos_passed") is True else (("OOS_FAIL", oos) if oos.get("oos_executed") is True else (decision, result)))
            except Exception: pass
        vp = ROOT / "research" / f"bc{bc}_validation_result.json"
        if vp.exists() and decision is None:
            try:
                validation = json.loads(vp.read_text(encoding="utf-8")); decision, result = (("VALIDATION_PASS", validation) if validation.get("validation_passed") is True else ("VALIDATION_FAIL", validation))
            except Exception: pass
        if decision in STRATEGY_DECISIONS:
            record(candidate, result, decision); data = load()
    _reaggregate(data); _atomic(data); return data


def stagnant(data=None, window=8):
    data = data or load(); events = [event for event in data.get("events", []) if event.get("decision") in STRATEGY_DECISIONS]
    return len(events) >= window and all(event.get("decision") in FAILURE_DECISIONS for event in events[-window:])


def rank_families(families, seed):
    """UCB family ranking with an explicit escape regime after repeated failures."""
    data = rebuild_from_artifacts(); families = list(dict.fromkeys(str(f) for f in families if str(f).strip()))
    if not families: return []
    total = max(1, sum(v.get("tested", 0) for v in data.get("families", {}).values())); is_stagnant = data.get("regime") == "STAGNANT"; ranked = []
    for index, family in enumerate(families):
        stats = data["families"].get(family, {"tested": 0, "pass": 0, "fail": 0, "score_sum": 0.0, "recent_failures": 0}); tested = int(stats.get("tested", 0)); mean = float(stats.get("score_sum", 0.0)) / tested if tested else 0.5; exploration = math.sqrt(math.log(total + 2) / (tested + 1)); recent_failures = int(stats.get("recent_failures", 0))
        value = (0.25 * mean + 1.25 * exploration - 0.18 * recent_failures) if is_stagnant else (mean + 0.45 * exploration)
        value += ((int(seed) + index) % 997) * 1e-9; ranked.append((value, family))
    return [family for _, family in sorted(ranked, reverse=True)]
