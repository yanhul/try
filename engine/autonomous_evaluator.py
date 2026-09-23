#!/usr/bin/env python3
"""Deterministic IS/Validation evaluator for registered, compiled, or mechanism-family candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .events import EventType
from .hypothesis_research import evaluate_split
from .hypotheses import HYPOTHESES
from research.cost_model import DEFAULT_COST_MODEL
from research.validation_policy import EVALUATION_SPEC, validation_gate

WINDOWS = {3, 5, 10, 20, 50, 100}
MECHANISMS = {
    "momentum_trend", "mean_reversion", "volatility", "smc_ict", "fvg_imbalance",
    "wyckoff_vsa_vpa", "vwap_volume_profile", "regime", "seasonality",
    "point_figure", "gann_reference",
}
EVENT_MECHANISMS = {"smc_ict", "fvg_imbalance"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def series_value(ctx, key):
    value = ctx.get("entry", {}).get(key)
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def discovered_value(spec, ctx):
    op = spec["operator"]; left = spec["left"]; right = spec.get("right"); w = spec.get("window")
    a = series_value(ctx, left); b = series_value(ctx, right) if right else None
    if a is None or (right and b is None): return None
    history = ctx.get("history", []) or []; vals = []
    for x in history:
        try: v = float(x.get(left))
        except (TypeError, ValueError): return None
        if not math.isfinite(v): return None
        vals.append(v)
    if op == "identity": value = a
    elif op == "difference": value = a - b
    elif op == "ratio":
        if b == 0: return None
        value = a / b
    elif op in {"rolling_mean", "rolling_std", "zscore", "lag", "delta", "rank"}:
        if not isinstance(w, int) or isinstance(w, bool) or w not in WINDOWS or len(vals) < w: return None
        window = vals[-w:]
        if op == "rolling_mean": value = sum(window) / w
        elif op == "rolling_std":
            mean = sum(window) / w; value = math.sqrt(sum((x - mean) ** 2 for x in window) / w)
        elif op == "zscore":
            mean = sum(window) / w; sd = math.sqrt(sum((x - mean) ** 2 for x in window) / w); value = (a - mean) / sd if sd else 0.0
        elif op == "lag": value = vals[-w]
        elif op == "delta": value = a - vals[-w]
        else: value = sum(x <= a for x in window) / w
    else: return None
    return value if math.isfinite(value) else None


def composite_predicate(spec):
    terms = spec.get("terms")
    if not isinstance(terms, list) or len(terms) != 2:
        raise ValueError("invalid_composite_terms")
    combine = spec.get("combine")
    if combine not in {"and", "or"}:
        raise ValueError("invalid_composite_operator")
    predicates = [discovered_predicate(term) for term in terms]
    def predicate(ctx, trade_direction):
        values = [p(ctx, trade_direction) for p in predicates]
        return all(values) if combine == "and" else any(values)
    return predicate

def discovered_predicate(spec):
    direction = spec["direction"]; threshold = float(spec["threshold"])
    def pred(ctx, trade_direction):
        value = discovered_value(spec, ctx)
        if value is None: return False
        signal_direction = "bullish" if direction == "above" else "bearish"
        return trade_direction == signal_direction and (value > threshold if direction == "above" else value < threshold)
    return pred


def _event(ctx, key):
    value = ctx.get(key); return value if isinstance(value, dict) else {}


def _event_value(ctx, key, field):
    value = _event(ctx, key).get(field)
    try: value = float(value)
    except (TypeError, ValueError): return None
    return value if math.isfinite(value) else None


def mechanism_predicate(spec):
    family = spec["mechanism_family"]; threshold = float(spec.get("threshold", 0.0)); comparison = spec.get("direction", "above")
    if family not in MECHANISMS: raise ValueError("invalid_mechanism_family")
    if family in {"volatility", "seasonality"}: raise ValueError(f"non_directional_mechanism_family:{family}")
    def pred(ctx, trade_direction):
        if family == "smc_ict":
            sweep, mss, fvg = _event(ctx, "sweep"), _event(ctx, "mss"), _event(ctx, "fvg")
            if (sweep.get("event_type") != EventType.LIQUIDITY_SWEEP.value or mss.get("event_type") != EventType.MSS.value or fvg.get("event_type") != EventType.FVG.value or sweep.get("direction") != mss.get("direction") or mss.get("direction") != trade_direction): return False
            sweep_price, mss_price = _event_value(ctx, "sweep", "price"), _event_value(ctx, "mss", "price")
            if sweep_price is None or mss_price is None or sweep_price <= 0: return False
            displacement = abs(mss_price - sweep_price) / sweep_price
            return displacement > threshold if comparison == "above" else displacement < threshold
        if family == "fvg_imbalance":
            fvg = _event(ctx, "fvg")
            if fvg.get("event_type") != EventType.FVG.value or fvg.get("direction") != trade_direction: return False
            lower, upper, entry = _event_value(ctx, "fvg", "lower"), _event_value(ctx, "fvg", "upper"), series_value(ctx, "close")
            if lower is None or upper is None or entry is None or entry <= 0: return False
            gap_fraction = abs(upper - lower) / entry
            return gap_fraction > threshold if comparison == "above" else gap_fraction < threshold
        value = mechanism_value(ctx, family)
        if value is None: return False
        if family == "mean_reversion":
            if trade_direction == "bullish": return value < -abs(threshold) if threshold else value < 0
            if trade_direction == "bearish": return value > abs(threshold) if threshold else value > 0
            return False
        expected = "bullish" if comparison == "above" else "bearish"
        return trade_direction == expected and (value > threshold if comparison == "above" else value < threshold)
    return pred


def mechanism_value(ctx, family):
    row = ctx.get("entry", {})
    if family == "momentum_trend": return row.get("momentum_trend")
    if family == "mean_reversion": return row.get("mean_reversion")
    if family == "volatility": return row.get("volatility")
    if family == "wyckoff_vsa_vpa": return row.get("wyckoff_vsa_vpa")
    if family == "vwap_volume_profile": return row.get("vwap_volume_profile")
    if family == "regime": return 1.0 if row.get("mtf_fast_bullish") else -1.0
    if family == "seasonality": return float(row.get("seasonality", 0))
    if family == "point_figure": return 1.0 if row.get("point_figure") == "X" else -1.0
    if family == "gann_reference": return row.get("gann_reference")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--candidate", required=True); ap.add_argument("--data", default="data/BTCUSDT_1h.csv"); ap.add_argument("--out", required=True); a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    candidate = json.loads(Path(a.candidate).read_text(encoding="utf-8")); hid = candidate["hypothesis_id"]; spec = candidate.get("discovery_spec") or {}
    if hid == "discovered_primitive":
        if not isinstance(spec, dict): raise SystemExit("UNEXECUTABLE_DISCOVERY_SPEC")
        predicate, candidate_universe, candidate_family = discovered_predicate(spec), "all_bars", "discovered_primitive"
    elif hid == "mechanism_family":
        if not isinstance(spec, dict): raise SystemExit("UNEXECUTABLE_MECHANISM_SPEC")
        predicate = mechanism_predicate(spec); family = spec.get("mechanism_family"); candidate_universe = "reference_event_ledger" if family in EVENT_MECHANISMS else "all_bars"; candidate_family = family
    elif hid == "composite_primitive":
        if not isinstance(spec, dict): raise SystemExit("UNEXECUTABLE_COMPOSITE_SPEC")
        predicate, candidate_universe, candidate_family = composite_predicate(spec), "all_bars", spec.get("mechanism_family")
    elif hid in HYPOTHESES:
        predicate, candidate_universe, candidate_family = HYPOTHESES[hid], "reference_event_ledger", None
    else: raise SystemExit(f"UNEXECUTABLE_HYPOTHESIS_ID:{hid}")
    data = (root / a.data).resolve(); bars = load_bars(data); splits = chronological_split(len(bars)); validate_splits(splits, len(bars))
    kwargs = {"candidate_universe": candidate_universe, "candidate_family": candidate_family, "candidate_spec": spec}; cost_model = DEFAULT_COST_MODEL
    is_result = evaluate_split(bars, splits[0].start, splits[0].end, predicate, EVALUATION_SPEC["stop_fraction"], EVALUATION_SPEC["reward_multiple"], cost_model=cost_model, **kwargs)
    val_result = evaluate_split(bars, splits[1].start, splits[1].end, predicate, EVALUATION_SPEC["stop_fraction"], EVALUATION_SPEC["reward_multiple"], cost_model=cost_model, **kwargs)
    validation_passed, gate_reasons = validation_gate(val_result["metrics"])
    cost_available = EVALUATION_SPEC.get("cost_model_status") == "AVAILABLE"
    net_gate = "PASS" if cost_available and validation_passed else ("COST_MODEL_REQUIRED" if not cost_available else "VALIDATION_QUALITY_FAILED")
    result = {"schema_version": 10, "bc": candidate["bc"], "parent_bc": candidate["parent_bc"], "hypothesis_id": hid, "candidate_hash": candidate["candidate_hash"], "discovery_spec": candidate.get("discovery_spec"), "oos_selection_used": False, "oos_executed": False, "dataset": {"path": str(data), "sha256": sha256(data), "bars": len(bars)}, "evaluation_spec": dict(EVALUATION_SPEC), "candidate_universe": candidate_universe, "cost_model": cost_model.metadata(), "IS": is_result, "VALIDATION": val_result, "gross_validation_passed": validation_passed, "validation_gate_reasons": gate_reasons, "net_validation_gate": net_gate, "validation_passed": bool(cost_available and validation_passed), "validation_basis": "NET_REQUIRED_FOR_PROMOTION"}
    out = root / a.out; out.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = root / "research" / "evaluation_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    evaluator_digest = sha256(Path(__file__))
    result["evaluator_digest"] = evaluator_digest
    cache_key = hashlib.sha256(json.dumps({
        "candidate_hash": candidate["candidate_hash"],
        "dataset_sha256": result["dataset"]["sha256"],
        "evaluator_digest": evaluator_digest,
        "evaluation_spec": EVALUATION_SPEC,
    }, sort_keys=True, default=str).encode()).hexdigest()
    cache_path = cache_dir / f"{cache_key}.json"
    cached = None
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            cached = None
    if isinstance(cached, dict) and (
            cached.get("candidate_hash") == candidate["candidate_hash"]
            and cached.get("dataset", {}).get("sha256") == result["dataset"]["sha256"]
            and cached.get("evaluator_digest") == evaluator_digest
            and cached.get("evaluation_spec") == result["evaluation_spec"]):
        result = cached
    else:
        cache_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"bc": candidate["bc"], "hypothesis_id": hid, "candidate_universe": candidate_universe, "gross_validation_passed": validation_passed, "gate_reasons": gate_reasons, "net_gate": net_gate}, indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
