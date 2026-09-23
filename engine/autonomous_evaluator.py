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


def _primitive_predicate(term):
    direction = term["direction"]; threshold = float(term["threshold"])
    def pred(ctx, trade_direction):
        value = discovered_value(term, ctx)
        if value is None:return False
        expected = "bullish" if direction == "above" else "bearish"
        return trade_direction == expected and (value > threshold if direction == "above" else value < threshold)
    return pred


def composite_predicate(spec):
    terms = spec.get("terms")
    if not isinstance(terms, list) or len(terms) != 2: raise ValueError("invalid_composite_terms")
    predicates = [_primitive_predicate(term) for term in terms]
    combine = spec.get("combine")
    if combine not in {"and", "or"}: raise ValueError("invalid_composite_operator")
    def pred(ctx, trade_direction):
        values = [p(ctx, trade_direction) for p in predicates]
        return all(values) if combine == "and" else any(values)
    return pred


def discovered_predicate(spec):
    return _primitive_predicate(spec)

