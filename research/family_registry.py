"""Canonical, layered research taxonomy.

The registry is the sole authority for discovery-family identity, taxonomy layer,
data-lane semantics, evaluator binding, and lineage metadata.

Backward compatibility: existing canonical_family IDs are preserved exactly.
The registry is intentionally extensible; it is not a claim that these are all
strategy families in existence. Newly discovered families must enter as
DISCOVERY_ONLY/DEFERRED until an explicit evaluator/data adapter exists.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Final

TAXONOMY_VERSION: Final[str] = "2.0.0"

@dataclass(frozen=True)
class DomainSpec:
    domain_id: str
    label: str

@dataclass(frozen=True)
class FamilySpec:
    family_id: str
    domain_id: str
    layer: str = "family"
    terms: tuple[str, ...] = ()
    data_requirement: str | None = None
    data_adapter: str | None = None
    discovery_enabled: bool = False
    evaluator_enabled: bool = False
    directional: bool = True
    evaluator_kind: str | None = None
    candidate_universe: str = "all_bars"
    status: str = "DISCOVERY_ONLY"

DOMAINS: Final[dict[str, DomainSpec]] = {
    "price_action": DomainSpec("price_action", "Price action / trend"),
    "statistical": DomainSpec("statistical", "Statistical / relative value"),
    "market_structure": DomainSpec("market_structure", "Market structure / imbalance"),
    "volume": DomainSpec("volume", "Volume / participation"),
    "derivatives": DomainSpec("derivatives", "Derivatives / carry"),
    "microstructure": DomainSpec("microstructure", "Order flow / execution"),
    "cross_sectional": DomainSpec("cross_sectional", "Cross-sectional / factor"),
    "regime": DomainSpec("regime", "Regime / state"),
    "calendar": DomainSpec("calendar", "Seasonality / calendar"),
    "onchain": DomainSpec("onchain", "On-chain"),
    "options": DomainSpec("options", "Options"),
    "prediction_market": DomainSpec("prediction_market", "Prediction markets"),
    "regional": DomainSpec("regional", "Regional market structure"),
}

_FAMILY_DATA: Final[tuple[FamilySpec, ...]] = (
    FamilySpec("momentum_trend", "price_action", terms=("momentum","trend","breakout","moving average"), discovery_enabled=True, evaluator_enabled=True, evaluator_kind="mechanism", data_requirement="ohlcv_bars", data_adapter="binance_ohlcv_csv", status="EXECUTABLE"),
    FamilySpec("mean_reversion", "statistical", terms=("mean reversion","mean-reversion","reversion","statistical arbitrage"), discovery_enabled=True, evaluator_enabled=True, evaluator_kind="mechanism", data_requirement="ohlcv_bars", data_adapter="binance_ohlcv_csv", status="EXECUTABLE"),
    FamilySpec("volatility", "statistical", terms=("volatility","variance","volatility breakout"), discovery_enabled=True, directional=False, evaluator_kind="mechanism"),
    FamilySpec("smc_ict", "market_structure", terms=("smart money","smc","ict","liquidity sweep","market structure","order block"), discovery_enabled=True, evaluator_enabled=True, evaluator_kind="mechanism", candidate_universe="reference_event_ledger", data_requirement="reference_event_ledger", data_adapter="reference_strategy", status="EXECUTABLE"),
    FamilySpec("fvg_imbalance", "market_structure", terms=("fair value gap","fvg","imbalance"), discovery_enabled=True, evaluator_enabled=True, evaluator_kind="mechanism", candidate_universe="reference_event_ledger", data_requirement="reference_event_ledger", data_adapter="reference_strategy", status="EXECUTABLE"),
    FamilySpec("wyckoff_vsa_vpa", "volume", terms=("wyckoff","vsa","volume spread","volume price analysis"), discovery_enabled=True, evaluator_enabled=True, evaluator_kind="mechanism", data_requirement="ohlcv_bars", data_adapter="binance_ohlcv_csv", status="EXECUTABLE"),
    FamilySpec("vwap_volume_profile", "volume", terms=("vwap","volume profile","anchored vwap"), discovery_enabled=True, evaluator_enabled=True, evaluator_kind="mechanism", data_requirement="ohlcv_bars", data_adapter="binance_ohlcv_csv", status="EXECUTABLE"),
    FamilySpec("funding_basis_carry", "derivatives", terms=("funding","basis","carry","perpetual"), discovery_enabled=True),
    FamilySpec("order_flow", "microstructure", terms=("order flow","orderflow","order book","lob imbalance","microprice"), discovery_enabled=True),
    FamilySpec("cross_sectional", "cross_sectional", terms=("cross-sectional","factor","rankic","icir","cross sectional"), discovery_enabled=True),
    FamilySpec("regime", "regime", terms=("regime","hidden markov","hmm","state switching"), discovery_enabled=True, evaluator_enabled=True, evaluator_kind="mechanism", data_requirement="ohlcv_bars", data_adapter="binance_ohlcv_csv", status="EXECUTABLE"),
    FamilySpec("seasonality", "calendar", terms=("seasonality","seasonal","day of week","calendar effect"), discovery_enabled=True, directional=False, evaluator_kind="mechanism"),
    FamilySpec("onchain", "onchain", terms=("on-chain","onchain","wallet","blockchain","solana"), discovery_enabled=True),
    FamilySpec("options", "options", terms=("options","implied volatility","skew","gamma"), discovery_enabled=True),
    FamilySpec("prediction_market", "prediction_market", terms=("prediction market","polymarket","kalshi","clob"), discovery_enabled=True),
    FamilySpec("execution_mev", "microstructure", terms=("execution","adverse selection","maker","taker","mev","slippage"), discovery_enabled=True),
    FamilySpec("china_a_share", "regional", terms=("china a-share","a-share","ashare","a share","chinese stock","chinese stocks","limit-up","limit up","连板","涨停","t+1","qlib","eastmoney","akshare","alpha158","factor mining","a股"), discovery_enabled=True),
    # These IDs are retained for evaluator compatibility but are explicitly primitives,
    # not discovery families. This prevents family/primitive layer confusion.
    FamilySpec("point_figure", "price_action", layer="primitive_reference", evaluator_enabled=True, evaluator_kind="reference_primitive", data_requirement="ohlcv_bars", data_adapter="binance_ohlcv_csv", status="EVALUATOR_ONLY"),
    FamilySpec("gann_reference", "price_action", layer="primitive_reference", evaluator_enabled=True, evaluator_kind="reference_primitive", data_requirement="ohlcv_bars", data_adapter="binance_ohlcv_csv", status="EVALUATOR_ONLY"),
)

FAMILIES: Final[dict[str, FamilySpec]] = {x.family_id: x for x in _FAMILY_DATA}
DISCOVERY_FAMILIES: Final[frozenset[str]] = frozenset(x.family_id for x in _FAMILY_DATA if x.discovery_enabled)
EXECUTABLE_FAMILIES: Final[frozenset[str]] = frozenset(x.family_id for x in _FAMILY_DATA if x.status == "EXECUTABLE" and x.evaluator_enabled and x.directional and x.evaluator_kind)
EVALUATOR_FAMILIES: Final[frozenset[str]] = frozenset(x.family_id for x in _FAMILY_DATA if x.evaluator_enabled and x.evaluator_kind)
EVENT_FAMILIES: Final[frozenset[str]] = frozenset(x.family_id for x in _FAMILY_DATA if x.candidate_universe == "reference_event_ledger")

def _canonical_registry_payload() -> list[dict]:
    return [
        {
            "family_id": x.family_id, "domain_id": x.domain_id, "layer": x.layer,
            "terms": list(x.terms), "discovery_enabled": x.discovery_enabled,
            "evaluator_enabled": x.evaluator_enabled, "directional": x.directional,
            "evaluator_kind": x.evaluator_kind, "candidate_universe": x.candidate_universe,
            "data_requirement": x.data_requirement, "data_adapter": x.data_adapter,
            "status": x.status,
        }
        for x in _FAMILY_DATA
    ]

REGISTRY_DIGEST: Final[str] = hashlib.sha256(
    json.dumps({"version": TAXONOMY_VERSION, "domains": {k: asdict(v) for k,v in DOMAINS.items()}, "families": _canonical_registry_payload()}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
).hexdigest()

def registry_metadata() -> dict[str, str]:
    return {"taxonomy_version": TAXONOMY_VERSION, "taxonomy_digest": REGISTRY_DIGEST}

def taxonomy_for_family(family_id: str) -> dict[str, str]:
    spec = get_family(family_id)
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_digest": REGISTRY_DIGEST,
        "domain_id": spec.domain_id,
        "layer": spec.layer,
        "canonical_family": spec.family_id,
        "status": spec.status,
    }

def get_family(family_id: str) -> FamilySpec:
    try:
        return FAMILIES[family_id]
    except KeyError as exc:
        raise ValueError(f"unknown_family:{family_id}") from exc

def require_evaluator(family_id: str) -> FamilySpec:
    spec = get_family(family_id)
    if family_id not in EVALUATOR_FAMILIES:
        raise ValueError(f"unevaluable_family:{family_id}")
    return spec

def require_executable(family_id: str) -> FamilySpec:
    spec = get_family(family_id)
    if family_id not in EXECUTABLE_FAMILIES:
        raise ValueError(f"unexecutable_family:{family_id}")
    return spec

def direction_for_row(row: dict, family_id: str) -> str | None:
    spec = get_family(family_id)
    if family_id not in EVALUATOR_FAMILIES:
        raise ValueError(f"unevaluable_family:{family_id}")
    if not spec.directional:
        raise ValueError(f"non_directional_family:{family_id}")
    if family_id == "mean_reversion":
        value = row.get("mean_reversion")
        return "bullish" if value is not None and value < 0 else "bearish" if value is not None and value > 0 else None
    if family_id == "regime":
        value = row.get("mtf_fast_bullish")
        return "bullish" if value is True else "bearish" if value is False else None
    if family_id == "point_figure":
        value = row.get("point_figure")
        return "bullish" if value == "X" else "bearish" if value == "O" else None
    key = {"momentum_trend":"momentum_trend","wyckoff_vsa_vpa":"wyckoff_vsa_vpa","vwap_volume_profile":"vwap_volume_profile","gann_reference":"gann_reference"}.get(family_id)
    value = row.get(key) if key else None
    return "bullish" if value is not None and value > 0 else "bearish" if value is not None and value < 0 else None

def validate_registry() -> None:
    if len(FAMILIES) != len(_FAMILY_DATA):
        raise AssertionError("duplicate_family_id")
    if not DOMAINS:
        raise AssertionError("empty_domain_registry")
    for spec in _FAMILY_DATA:
        if spec.domain_id not in DOMAINS:
            raise AssertionError(f"unknown_domain:{spec.family_id}")
        if spec.status not in {"EXECUTABLE","DISCOVERY_ONLY","EVALUATOR_ONLY"}:
            raise AssertionError(f"invalid_status:{spec.family_id}")
        if spec.layer == "primitive_reference" and spec.discovery_enabled:
            raise AssertionError(f"primitive_cannot_be_discovery_family:{spec.family_id}")
        if spec.evaluator_enabled and not spec.evaluator_kind:
            raise AssertionError(f"evaluator_kind_missing:{spec.family_id}")
        if spec.evaluator_enabled and spec.directional and spec.family_id not in EXECUTABLE_FAMILIES:
            raise AssertionError(f"directional_family_not_executable:{spec.family_id}")
        if spec.status in {"EXECUTABLE", "EVALUATOR_ONLY"} and (not spec.data_requirement or not spec.data_adapter):
            raise AssertionError(f"data_lane_incomplete:{spec.family_id}")
        if spec.candidate_universe not in {"all_bars","reference_event_ledger"}:
            raise AssertionError(f"invalid_candidate_universe:{spec.family_id}")
        if spec.status == "EXECUTABLE" and spec.family_id not in EXECUTABLE_FAMILIES:
            raise AssertionError(f"executable_status_without_adapter:{spec.family_id}")

validate_registry()
