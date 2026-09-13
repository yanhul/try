from datetime import datetime, timedelta, timezone

from engine.autonomous_evaluator import discovered_predicate, mechanism_predicate
from engine.events import MarketBar
from engine.hypothesis_research import prepare_split


def bars(n=12):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [MarketBar(start + timedelta(hours=i), 100+i, 101+i, 99+i, 100+i, 1000+i) for i in range(n)]


def test_autonomous_bar_universe_is_not_reference_event_ledger():
    data = bars()
    prepared = prepare_split(data, 1, len(data), candidate_universe="all_bars", candidate_family="momentum_trend")
    assert prepared.candidate_universe == "all_bars"
    assert len(prepared.ledger) == len(data) - 1
    assert len(prepared.contexts) == len(prepared.ledger)


def test_discovered_direction_controls_trade_side():
    spec = {"operator": "identity", "left": "close", "threshold": 100, "direction": "above"}
    predicate = discovered_predicate(spec)
    ctx = {"entry": {"close": 101}, "history": [{"close": 100}, {"close": 101}]}
    assert predicate(ctx, "bullish")
    assert not predicate(ctx, "bearish")


def test_mean_reversion_family_uses_reversion_direction():
    predicate = mechanism_predicate({"mechanism_family": "mean_reversion", "threshold": 0, "direction": "above"})
    assert predicate({"entry": {"mean_reversion": -1.2}}, "bullish")
    assert predicate({"entry": {"mean_reversion": 1.2}}, "bearish")
    assert not predicate({"entry": {"mean_reversion": 1.2}}, "bullish")
