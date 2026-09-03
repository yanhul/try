"""Canonical strategy specification and provenance for auditable research."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .feature_library import FEATURE_CATALOG

SCHEMA_VERSION = 1


def canonicalize(spec: dict[str, Any]) -> dict[str, Any]:
    features = spec.get("features", {})
    unknown = set(features) - set(FEATURE_CATALOG)
    if unknown:
        raise ValueError(f"unknown feature domains: {sorted(unknown)}")
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": str(spec.get("strategy_id", "unnamed")),
        "source": spec.get("source", {"type": "native", "uri": None}),
        "hypothesis": str(spec.get("hypothesis", "")),
        "market": spec.get("market", {}),
        "timeframe": spec.get("timeframe"),
        "features": features,
        "entry": spec.get("entry", {}),
        "exit": spec.get("exit", {}),
        "risk": spec.get("risk", {}),
        "execution": spec.get("execution", {"fees": 0.0, "slippage": 0.0}),
    }
    return normalized


def strategy_hash(spec: dict[str, Any]) -> str:
    payload = json.dumps(canonicalize(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def provenance(spec: dict[str, Any], *, original_code: str | None = None) -> dict[str, Any]:
    normalized = canonicalize(spec)
    result = {
        "strategy_hash": strategy_hash(normalized),
        "source": normalized["source"],
        "hypothesis": normalized["hypothesis"],
        "schema_version": SCHEMA_VERSION,
    }
    if original_code is not None:
        result["original_code_sha256"] = hashlib.sha256(original_code.encode("utf-8")).hexdigest()
    return result
