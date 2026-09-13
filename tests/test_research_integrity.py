import pytest

from engine.autonomous_evaluator import mechanism_predicate
from engine.hypothesis_research import prepare_split
from engine.events import Direction
from research.cost_model import DEFAULT_COST_MODEL


def test_event_mechanism_is_not_unconditional():
    pred = mechanism_predicate({
        "mechanism_family": "smc_ict",
        "threshold": 0.0,
        "direction": "above",
    })
    ctx = {
        "sweep": {"event_type": "NOT_A_SWEEP", "direction": "bullish", "price": 100},
        "mss": {"event_type": "NOT_MSS", "direction": "bullish", "price": 101},
        "fvg": {"event_type": "NOT_FVG", "direction": "bullish", "price": 102},
    }
    assert pred(ctx, Direction.BULLISH.value) is False


def test_smc_predicate_requires_real_event_chain():
    pred = mechanism_predicate({
        "mechanism_family": "smc_ict",
        "threshold": 0.005,
        "direction": "above",
    })
    ctx = {
        "sweep": {"event_type": "LIQUIDITY_SWEEP", "direction": "bullish", "price": 100},
        "mss": {"event_type": "MSS", "direction": "bullish", "price": 101},
        "fvg": {"event_type": "FVG", "direction": "bullish", "price": 101.5},
        "entry": {"close": 101.5},
    }
    assert pred(ctx, Direction.BULLISH.value) is True


def test_fvg_predicate_uses_gap_size():
    pred = mechanism_predicate({
        "mechanism_family": "fvg_imbalance",
        "threshold": 0.01,
        "direction": "above",
    })
    ctx = {
        "fvg": {
            "event_type": "FVG",
            "direction": "bullish",
            "lower": 100.0,
            "upper": 102.0,
        },
        "entry": {"close": 101.0},
    }
    assert pred(ctx, Direction.BULLISH.value) is True


def test_unknown_all_bars_family_fails_closed():
    bars = [
        type("Bar", (), {"timestamp": None, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10.0})(),
        type("Bar", (), {"timestamp": None, "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 12.0})(),
        type("Bar", (), {"timestamp": None, "open": 101.5, "high": 103.0, "low": 101.0, "close": 102.5, "volume": 11.0})(),
    ]
    with pytest.raises(ValueError, match="unsupported_all_bars_family"):
        prepare_split(bars, 0, 3, candidate_universe="all_bars", candidate_family="unknown")


def test_default_cost_model_is_real_and_available():
    metadata = DEFAULT_COST_MODEL.metadata()
    assert metadata["status"] == "AVAILABLE"
    assert metadata["fee_bps_per_side"] > 0
    assert metadata["slippage_bps_per_side"] > 0
