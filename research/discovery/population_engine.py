#!/usr/bin/env python3
"""Multi-round research population engine.

Absorbs the useful architecture pattern from LLM/evolutionary alpha-mining systems:
LLM/research sources expand the population; deterministic rounds narrow it; only
screen survivors enter executable research. No round may promote directly to OOS.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DISCOVERY = ROOT / "research" / "discovery"
LANES = DISCOVERY / "source_lanes.json"
LATEST = DISCOVERY / "latest.json"
ARCHIVE = DISCOVERY / "source_archive.json"
POPULATION = DISCOVERY / "population.json"
SURVIVORS = DISCOVERY / "survivors.json"
QUEUE = DISCOVERY / "research_queue.json"

FAMILY_TERMS = {
    "momentum_trend": ("momentum", "trend", "breakout", "moving average"),
    "mean_reversion": ("mean reversion", "mean-reversion", "reversion", "statistical arbitrage"),
    "volatility": ("volatility", "variance", "volatility breakout"),
    "smc_ict": ("smart money", "smc", "ict", "liquidity sweep", "market structure", "order block"),
    "fvg_imbalance": ("fair value gap", "fvg", "imbalance"),
    "wyckoff_vsa_vpa": ("wyckoff", "vsa", "volume spread", "volume price analysis"),
    "vwap_volume_profile": ("vwap", "volume profile", "anchored vwap"),
    "funding_basis_carry": ("funding", "basis", "carry", "perpetual"),
    "order_flow": ("order flow", "orderflow", "order book", "lob imbalance", "microprice"),
    "cross_sectional": ("cross-sectional", "factor", "rankic", "icir", "cross sectional"),
    "regime": ("regime", "hidden markov", "hmm", "state switching"),
    "seasonality": ("seasonality", "seasonal", "day of week", "calendar effect"),
    "onchain": ("on-chain", "onchain", "wallet", "blockchain", "solana"),
    "options": ("options", "implied volatility", "skew", "gamma"),
    "prediction_market": ("prediction market", "polymarket", "kalshi", "clob"),
    "execution_mev": ("execution", "adverse selection", "maker", "taker", "mev", "slippage"),
}

EXECUTABLE_FAMILIES = {
    "momentum_trend", "mean_reversion", "volatility", "smc_ict",
    "fvg_imbalance", "wyckoff_vsa_vpa", "vwap_volume_profile",
    "regime", "seasonality", "cross_sectional",
}


def _text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(k, "")) for k in ("title", "description", "raw", "query")).lower()


def classify(item: dict[str, Any]) -> str:
    text = _text(item)
    scores = {family: sum(text.count(term) for term in terms) for family, terms in FAMILY_TERMS.items()}
    best, score = max(scores.items(), key=lambda x: x[1])
    return best if score else "unknown"


def source_id(item: dict[str, Any]) -> str:
    canonical = str(item.get("url") or item.get("title") or item.get("raw") or item.get("query"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _xml_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def expand_source(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand an arXiv feed into one candidate per paper; never treat a feed as one paper."""
    if item.get("source") != "arxiv" or not item.get("raw"):
        return [item]
    try:
        root = ET.fromstring(item["raw"])
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entries = root.findall("a:entry", ns)
        expanded = []
        for entry in entries:
            paper_id = _xml_text(entry.find("a:id", ns))
            title = _xml_text(entry.find("a:title", ns)) or item.get("query")
            summary = _xml_text(entry.find("a:summary", ns))
            published = _xml_text(entry.find("a:published", ns))
            link = next((x.attrib.get("href") for x in entry.findall("a:link", ns) if x.attrib.get("href")), paper_id)
            expanded.append({"source":"arxiv","query":item.get("query"),"title":title,"url":link or paper_id,"description":summary,"updated_at":published})
        return expanded or [{k:v for k,v in item.items() if k != "raw"}]
    except ET.ParseError:
        return []


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    family = classify(raw)
    return {"candidate_id":source_id(raw),"source":raw.get("source","unknown"),"source_url":raw.get("url"),"title":raw.get("title") or raw.get("query"),"description":raw.get("description"),"family":family,"query":raw.get("query"),"source_timestamp":raw.get("updated_at"),"lineage":{"source":source_id(raw),"family":family,"rounds":[]}}


def round1_source_quality(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out=[]; seen=set()
    for item in items:
        key=item.get("source_url") or re.sub(r"\s+"," ",str(item.get("title","")).lower()).strip()
        if not key or key in seen: continue
        seen.add(key)
        if item.get("source") in {"github","arxiv"}:
            item["lineage"]["rounds"].append({"round":1,"decision":"PASS_SOURCE"}); out.append(item)
    return out


def round2_feasibility(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]],list[dict[str, Any]]]:
    executable=[]; deferred=[]
    for item in items:
        family=item["family"]
        if family in EXECUTABLE_FAMILIES:
            item["lineage"]["rounds"].append({"round":2,"decision":"PASS_EXECUTABLE_DATA_LANE"}); executable.append(item)
        else:
            item["lineage"]["rounds"].append({"round":2,"decision":"DEFER_DATA_LANE","family":family}); deferred.append(item)
    return executable,deferred


def round3_diversity(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate exact source titles, then interleave families deterministically.

    The old implementation sorted by family, which clustered all mean-reversion
    sources together. Interleaving keeps the executable queue diverse without
    letting an LLM choose which family is tested next.
    """
    groups: dict[str,list[dict[str,Any]]] = {}
    seen=set()
    for item in sorted(items,key=lambda x:(x["family"],x["title"] or "")):
        key=(item["family"],re.sub(r"[^a-z0-9]+"," ",str(item["title"]).lower()).strip())
        if key in seen: continue
        seen.add(key); groups.setdefault(item["family"],[]).append(item)
    out=[]
    families=sorted(groups)
    depth=0
    while True:
        added=False
        for family in families:
            bucket=groups[family]
            if depth < len(bucket):
                item=bucket[depth]
                item["lineage"]["rounds"].append({"round":3,"decision":"PASS_DIVERSITY_DEDUP","family_order":"round_robin"})
                out.append(item); added=True
        if not added: break
        depth += 1
    return out


def _load_discovery_sources() -> tuple[list[dict[str, Any]],str]:
    if ARCHIVE.exists():
        try:
            payload=json.loads(ARCHIVE.read_text(encoding="utf-8")); sources=payload.get("sources",[])
            if isinstance(sources,list): return [x for x in sources if isinstance(x,dict) and not x.get("error")],"archive"
        except (OSError,json.JSONDecodeError,TypeError): pass
    if LATEST.exists():
        try:
            payload=json.loads(LATEST.read_text(encoding="utf-8")); sources=payload.get("results",[])
            if isinstance(sources,list): return [x for x in sources if isinstance(x,dict) and not x.get("error")],"latest_fallback"
        except (OSError,json.JSONDecodeError,TypeError): pass
    return [],"empty"


def build()->dict[str,Any]:
    raw_sources,source_store=_load_discovery_sources(); expanded=[]
    for raw in raw_sources: expanded.extend(expand_source(raw))
    normalized=[normalize(x) for x in expanded]; r1=round1_source_quality(normalized); executable,deferred=round2_feasibility(r1); survivors=round3_diversity(executable)
    payload={"schema_version":3,"architecture":"durable_source_archive -> expand -> normalize_dedup -> feasibility -> diversity -> survivor_registry -> executable_translation","source_store":source_store,"policy_authority":"research/campaign_policy.json","counts":{"raw":len(raw_sources),"expanded":len(expanded),"normalized":len(normalized),"round1":len(r1),"deferred":len(deferred),"survivors":len(survivors)},"population":normalized,"deferred":deferred}
    POPULATION.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    SURVIVORS.write_text(json.dumps({"schema_version":3,"status":"SCREEN_SURVIVORS_NOT_PERFORMANCE_PROMOTION","survivors":survivors},indent=2),encoding="utf-8")
    QUEUE.write_text(json.dumps({"schema_version":3,"status":"READY_FOR_EXECUTABLE_TRANSLATION","candidates":survivors},indent=2),encoding="utf-8")
    return payload

if __name__=="__main__":
    result=build(); print("POPULATION_ENGINE_DONE",json.dumps(result["counts"],sort_keys=True))
