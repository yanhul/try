import json
from datetime import datetime, timezone, timedelta

from engine.feature_library import causal_features, evaluate_filters, catalog
from engine.strategy_spec import canonicalize, provenance, strategy_hash
from engine.events import MarketBar


def make_bars(n=30):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [MarketBar(timestamp=base + timedelta(hours=i), open=100+i*0.1, high=101+i*0.1, low=99+i*0.1, close=100.5+i*0.1, volume=1000+i*10) for i in range(n)]


def test_catalog_contains_all_research_domains():
    c = catalog()
    for domain in ["market_structure", "wyckoff", "vsa", "vpa", "vwap", "volume_profile", "mtf", "volatility", "gann", "point_figure"]:
        assert domain in c


def test_features_are_causal_shape():
    bs = make_bars()
    a = causal_features(bs, 10)
    b = causal_features(bs, 20)
    assert set(a) == set(b)
    assert all(isinstance(v, float) for v in a.values())


def test_filter_is_deterministic():
    bs = make_bars()
    f = {"lookback": 10, "relative_volume": {"min": 0.5}, "vwap_distance": {"min": -0.1, "max": 0.1}}
    assert evaluate_filters(bs, 20, f) == evaluate_filters(bs, 20, f)


def test_strategy_provenance_is_stable():
    spec = canonicalize({"strategy_id": "x", "source": {"type": "tradingview", "uri": "example"}, "hypothesis": "test", "features": {"filters": {"relative_volume": {"min": 1.0}}}})
    assert strategy_hash(spec) == strategy_hash(spec)
    assert provenance(spec)["strategy_hash"] == strategy_hash(spec)
    json.dumps(provenance(spec))
