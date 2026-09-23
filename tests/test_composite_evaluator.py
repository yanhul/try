from engine.autonomous_evaluator import composite_predicate

def _ctx(close, volume):
    return {
        "entry": {"close": close, "volume": volume},
        "history": [{"close": 10.0, "volume": 100.0}, {"close": 11.0, "volume": 110.0}],
    }

def test_composite_and_requires_both_terms():
    pred = composite_predicate({
        "combine": "and",
        "terms": [
            {"operator": "identity", "left": "close", "threshold": 10.0, "direction": "above"},
            {"operator": "identity", "left": "volume", "threshold": 100.0, "direction": "above"},
        ],
    })
    assert pred(_ctx(11, 120), "bullish")
    assert not pred(_ctx(11, 90), "bullish")

def test_composite_or_accepts_either_term():
    pred = composite_predicate({
        "combine": "or",
        "terms": [
            {"operator": "identity", "left": "close", "threshold": 20.0, "direction": "above"},
            {"operator": "identity", "left": "volume", "threshold": 100.0, "direction": "above"},
        ],
    })
    assert pred(_ctx(11, 120), "bullish")
    assert not pred(_ctx(11, 90), "bullish")
