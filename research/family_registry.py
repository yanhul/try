"""Canonical research-family registry.

One vocabulary is authoritative for discovery, translation, and evaluation.
Unknown or incomplete families fail closed to DEFER; they are never executed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class FamilySpec:
    family_id: str
    terms: tuple[str, ...] = ()
    discovery_enabled: bool = False
    evaluator_enabled: bool = False
    directional: bool = True
    evaluator_kind: str | None = None
    candidate_universe: str = "all_bars"


_FAMILY_DATA: Final[tuple[FamilySpec, ...]] = (
    FamilySpec("momentum_trend", ("momentum", "trend", "breakout", "moving average"), True, True, True, "mechanism"),
    FamilySpec("mean_reversion", ("mean reversion", "mean-reversion", "reversion", "statistical arbitrage"), True, True, True, "mechanism"),
    FamilySpec("volatility", ("volatility", "variance", "volatility breakout"), True, False, False, "mechanism"),
    FamilySpec("smc_ict", ("smart money", "smc", "ict", "liquidity sweep", "market structure", "order block"), True, True, True, "mechanism", "reference_event_ledger"),
    FamilySpec("fvg_imbalance", ("fair value gap", "fvg", "imbalance"), True, True, True, "mechanism", "reference_event_ledger"),
    FamilySpec("wyckoff_vsa_vpa", ("wyckoff", "vsa", "volume spread", "volume price analysis"), True, True, True, "mechanism"),
    FamilySpec("vwap_volume_profile", ("vwap", "volume profile", "anchored vwap"), True, True, True, "mechanism"),
    FamilySpec("funding_basis_carry", ("funding", "basis", "carry", "perpetual"), True, False),
    FamilySpec("order_flow", ("order flow", "orderflow", "order book", "lob imbalance", "microprice"), True, False),
    FamilySpec("cross_sectional", ("cross-sectional", "factor", "rankic", "icir", "cross sectional"), True, False),
    FamilySpec("regime", ("regime", "hidden markov", "hmm", "state switching"), True, True, True, "mechanism"),
    FamilySpec("seasonality", ("seasonality", "seasonal", "day of week", "calendar effect"), True, False, False, "mechanism"),
    FamilySpec("onchain", ("on-chain", "onchain", "wallet", "blockchain", "solana"), True, False),
    FamilySpec("options", ("options", "implied volatility", "skew", "gamma"), True, False),
    FamilySpec("prediction_market", ("prediction market", "polymarket", "kalshi", "clob"), True, False),
    FamilySpec("execution_mev", ("execution", "adverse selection", "maker", "taker", "mev", "slippage"), True, False),
    FamilySpec("china_a_share", ("china a-share", "a-share", "ashare", "a share", "chinese stock", "chinese stocks", "limit-up", "limit up", "连板", "涨停", "t+1", "qlib", "eastmoney", "akshare", "alpha158", "factor mining", "a股"), True, False),
    # Evaluator-only families are explicit and therefore cannot accidentally become discovery families.
    FamilySpec("point_figure", (), False, True, True, "mechanism"),
    FamilySpec("gann_reference", (), False, True, True, "mechanism"),
)

FAMILIES: Final[dict[str, FamilySpec]] = {x.family_id: x for x in _FAMILY_DATA}
DISCOVERY_FAMILIES: Final[frozenset[str]] = frozenset(x.family_id for x in _FAMILY_DATA if x.discovery_enabled)
EXECUTABLE_FAMILIES: Final[frozenset[str]] = frozenset(
    x.family_id for x in _FAMILY_DATA if x.evaluator_enabled and x.directional and x.evaluator_kind
)
EVENT_FAMILIES: Final[frozenset[str]] = frozenset(
    x.family_id for x in _FAMILY_DATA if x.candidate_universe == "reference_event_ledger"
)


def get_family(family_id: str) -> FamilySpec:
    try:
        return FAMILIES[family_id]
    except KeyError as exc:
        raise ValueError(f"unknown_family:{family_id}") from exc


def require_executable(family_id: str) -> FamilySpec:
    spec = get_family(family_id)
    if family_id not in EXECUTABLE_FAMILIES:
        raise ValueError(f"unexecutable_family:{family_id}")
    return spec


def direction_for_row(row: dict, family_id: str) -> str | None:
    spec = require_executable(family_id)
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
    key = {
        "momentum_trend": "momentum_trend",
        "wyckoff_vsa_vpa": "wyckoff_vsa_vpa",
        "vwap_volume_profile": "vwap_volume_profile",
        "gann_reference": "gann_reference",
    }.get(family_id)
    value = row.get(key) if key else None
    return "bullish" if value is not None and value > 0 else "bearish" if value is not None and value < 0 else None


def validate_registry() -> None:
    if len(FAMILIES) != len(_FAMILY_DATA):
        raise AssertionError("duplicate_family_id")
    for spec in _FAMILY_DATA:
        if spec.evaluator_enabled and not spec.evaluator_kind:
            raise AssertionError(f"evaluator_kind_missing:{spec.family_id}")
        if spec.evaluator_enabled and spec.directional and spec.family_id not in EXECUTABLE_FAMILIES:
            raise AssertionError(f"directional_family_not_executable:{spec.family_id}")
        if spec.candidate_universe not in {"all_bars", "reference_event_ledger"}:
            raise AssertionError(f"invalid_candidate_universe:{spec.family_id}")


validate_registry()
