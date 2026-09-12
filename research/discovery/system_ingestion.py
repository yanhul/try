#!/usr/bin/env python3
"""Deterministic universal ingestion registry for every discovered research source.

Discovery is provenance only. Every successful scanned source is retained, deduplicated,
classified, and assigned an explicit translation status. No source is silently dropped
because its mechanism is unknown; unknowns remain UNKNOWN rather than becoming alpha.
"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "research/discovery/source_archive.json"
CHINA = ROOT / "research/discovery/china_a_share_sources.json"
OUT = ROOT / "research/discovery/system_registry.json"

FAMILY_RULES = [
    ("china_a_share", ["a-share", "a share", "limit-up", "limit up", "t+1", "cn-trader"]),
    ("mean_reversion", ["mean reversion", "statistical arbitrage", "pairs", "reversal"]),
    ("momentum", ["momentum", "trend following", "breakout"]),
    ("volatility", ["volatility", "stochastic", "volatility breakout", "options"]),
    ("smc_ict", ["smc", "ict", "liquidity sweep", "fair value gap", "fvg", "order block"]),
    ("wyckoff_vpa", ["wyckoff", "vsa", "vpa", "volume price"]),
    ("execution_mev", ["mev", "maker", "adverse selection", "execution"]),
    ("order_flow", ["order flow", "order book", "microprice", "imbalance"]),
    ("funding_basis", ["funding rate", "basis", "carry", "arbitrage"]),
    ("onchain", ["on chain", "on-chain", "solana", "liquidity trading"]),
    ("prediction_market", ["prediction market", "clob", "polymarket"]),
    ("factor", ["factor", "cross sectional", "multi-factor", "alpha mining"]),
    ("ml_rl", ["machine learning", "xgboost", "reinforcement learning", "hidden markov", "symbolic regression"]),
]
MECHANISM_RULES = [
    ("cross_sectional_factor", ["factor", "cross sectional", "multi-factor", "rank"]),
    ("mean_reversion", ["mean reversion", "pairs", "statistical arbitrage", "reversal"]),
    ("momentum_trend", ["momentum", "trend following", "breakout"]),
    ("liquidity_structure", ["smc", "ict", "liquidity sweep", "fair value gap", "fvg", "order block"]),
    ("volume_structure", ["wyckoff", "vsa", "vpa", "volume price"]),
    ("order_flow", ["order flow", "order book", "microprice", "imbalance"]),
    ("carry_basis", ["funding rate", "basis", "carry"]),
    ("execution_mev", ["mev", "maker", "adverse selection", "execution"]),
    ("volatility", ["volatility", "stochastic", "options", "gamma", "skew"]),
    ("limit_rule", ["limit-up", "limit up", "t+1", "lot rounding"]),
    ("onchain_flow", ["on chain", "on-chain", "solana"]),
    ("prediction_market", ["prediction market", "clob", "polymarket"]),
    ("ml_rl", ["machine learning", "xgboost", "reinforcement learning", "hidden markov"]),
]

def norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()

def classify(text: str, rules: list[tuple[str, list[str]]], default: str) -> str:
    scores = [(sum(1 for token in tokens if token in text), family) for family, tokens in rules]
    scores.sort(key=lambda x: (-x[0], x[1]))
    return scores[0][1] if scores and scores[0][0] else default

def source_id(item: dict) -> str:
    basis = str(item.get("url") or item.get("title") or item.get("raw") or item.get("query") or "")
    return "SRC-" + hashlib.sha256(basis.encode()).hexdigest()[:16]

def main() -> None:
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8")) if ARCHIVE.exists() else {"sources": []}
    items = [x for x in archive.get("sources", []) if isinstance(x, dict) and not x.get("error")]
    if CHINA.exists():
        china = json.loads(CHINA.read_text(encoding="utf-8"))
        items += [{"source": "curated", "title": x.get("name"), "url": x.get("url"),
                   "description": x.get("description", ""), "lane": "china_a_share",
                   "curated": True} for x in china.get("sources", []) if isinstance(x, dict)]

    by_key = {}
    for item in items:
        key = item.get("url") or item.get("title") or item.get("raw") or item.get("query")
        if key and key not in by_key:
            by_key[key] = item

    systems = []
    for item in sorted(by_key.values(), key=lambda x: (str(x.get("source", "")), str(x.get("title", "")), str(x.get("url", "")))):
        text = norm(" ".join(str(item.get(k, "")) for k in ("title", "description", "query", "lane")))
        family = item.get("lane") or classify(text, FAMILY_RULES, "unclassified")
        mechanism = classify(text, MECHANISM_RULES, "unknown")
        is_system = bool(item.get("url") and (item.get("title") or item.get("description")))
        systems.append({
            "source_id": source_id(item),
            "source": item.get("source", "unknown"),
            "title": item.get("title"),
            "url": item.get("url"),
            "description": item.get("description"),
            "query": item.get("query"),
            "family": family,
            "mechanism": mechanism,
            "is_system": is_system,
            "provenance_only": True,
            "translation_status": "PENDING_INDEPENDENT_TRANSLATION" if is_system else "NOT_A_SYSTEM_RECORD",
            "executable": False,
        })

    payload = {
        "schema_version": 1,
        "contract": "every successful scanned source is represented; deduplication is deterministic; provenance never implies alpha",
        "scan_inputs": ["source_archive.json", "china_a_share_sources.json"],
        "total_records": len(systems),
        "system_records": sum(1 for x in systems if x["is_system"]),
        "records": systems,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"SYSTEM_INGESTION_DONE records={len(systems)} systems={payload['system_records']}")

if __name__ == "__main__":
    main()
