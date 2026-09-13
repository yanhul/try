from datetime import datetime, timedelta

from engine.events import MarketBar
from engine.hypothesis_research import prepare_split
from engine.autonomous_evaluator import mechanism_predicate


def test_mechanism_family_candidate_is_executable_in_shared_context():
    bars = [
        MarketBar(datetime(2026, 1, 1) + timedelta(hours=i), 100+i, 101+i, 99+i, 100.5+i, 1000+i)
        for i in range(80)
    ]
    prepared = prepare_split(bars, 0, len(bars))
    predicate = mechanism_predicate({"mechanism_family": "momentum_trend", "threshold": -1.0, "direction": "above"})
    assert prepared.history == bars
    for ctx in prepared.contexts:
        assert "momentum_trend" in ctx["entry"]
        assert predicate(ctx, "bullish") is True


def test_event_mechanism_predicates_use_shared_ledger_context():
    bars = [
        MarketBar(datetime(2026, 1, 1) + timedelta(hours=i), 100+i, 101+i, 99+i, 100.5+i, 1000+i)
        for i in range(80)
    ]
    prepared = prepare_split(bars, 0, len(bars))
    for ctx in prepared.contexts:
        assert ctx["entry"]["smc_ict"] == 1.0
        assert ctx["entry"]["fvg_imbalance"] == 1.0
        assert mechanism_predicate({"mechanism_family":"smc_ict","threshold":0,"direction":"above"})(ctx,"bullish")
        assert mechanism_predicate({"mechanism_family":"fvg_imbalance","threshold":0,"direction":"above"})(ctx,"bullish")
