from datetime import datetime, timedelta

from engine.events import MarketBar
from engine.hypothesis_research import prepare_split
from engine.autonomous_evaluator import mechanism_predicate


def test_mechanism_family_candidate_is_executable_in_shared_context():
    bars = [
        MarketBar(datetime(2026, 1, 1) + timedelta(hours=i), 100+i, 101+i, 99+i, 100.5+i, 1000+i)
        for i in range(80)
    ]
    prepared = prepare_split(bars, 0, len(bars), candidate_universe="all_bars", candidate_family="momentum_trend")
    predicate = mechanism_predicate({"mechanism_family": "momentum_trend", "threshold": -1.0, "direction": "above"})
    assert prepared.history == bars
    for ctx in prepared.contexts:
        assert "momentum_trend" in ctx["entry"]
        assert predicate(ctx, "bullish") is True


def test_event_mechanism_predicates_are_not_unconditional():
    ctx = {
        "sweep": {"event_type": "NOT_A_SWEEP", "direction": "bullish", "price": 100},
        "mss": {"event_type": "NOT_MSS", "direction": "bullish", "price": 101},
        "fvg": {"event_type": "NOT_FVG", "direction": "bullish", "price": 102},
        "entry": {"close": 102},
    }
    for family in ("smc_ict", "fvg_imbalance"):
        predicate = mechanism_predicate({"mechanism_family": family, "threshold": 0, "direction": "above"})
        assert predicate(ctx, "bullish") is False


def test_smc_predicate_requires_real_chain():
    predicate = mechanism_predicate({"mechanism_family": "smc_ict", "threshold": 0.005, "direction": "above"})
    ctx = {
        "sweep": {"event_type": "LIQUIDITY_SWEEP", "direction": "bullish", "price": 100},
        "mss": {"event_type": "MSS", "direction": "bullish", "price": 101},
        "fvg": {"event_type": "FVG", "direction": "bullish", "price": 101.5, "lower": 100.5, "upper": 102},
        "entry": {"close": 101.5},
    }
    assert predicate(ctx, "bullish") is True


def test_fvg_predicate_uses_gap_size():
    predicate = mechanism_predicate({"mechanism_family": "fvg_imbalance", "threshold": 0.01, "direction": "above"})
    ctx = {
        "fvg": {"event_type": "FVG", "direction": "bullish", "lower": 100.0, "upper": 102.0},
        "entry": {"close": 101.0},
    }
    assert predicate(ctx, "bullish") is True
