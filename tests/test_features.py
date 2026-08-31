from datetime import datetime, timedelta, timezone
from engine.events import MarketBar
from engine.features import extract_features


def _bars(n=5):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [MarketBar(start + timedelta(hours=i), 100+i, 102+i, 99+i, 101+i, 10+i) for i in range(n)]


def test_features_are_causal_and_schema_is_stable():
    bars = _bars()
    features = extract_features(bars, window=3)
    assert len(features) == len(bars)
    assert features[0]["volume_sma"] == 10
    assert features[2]["volume_sma"] == 11
    assert features[2]["higher_high"] is True
    assert features[2]["lower_low"] is False


def test_zero_range_is_safe():
    b = MarketBar(datetime(2026,1,1,tzinfo=timezone.utc),100,100,100,100,10)
    f = extract_features([b])[0]
    assert f["close_location"] == 0.5
    assert f["effort_result"] is None
