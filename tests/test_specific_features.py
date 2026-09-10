from datetime import datetime, timedelta, timezone

from engine.events import MarketBar
from engine.specific_features import extract_specific_features


def _bars():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(start, 100, 102, 99, 101, 10),
        MarketBar(start + timedelta(hours=1), 101, 103, 100, 102, 11),
        MarketBar(start + timedelta(hours=2), 102, 104, 101, 103, 12),
        MarketBar(start + timedelta(hours=3), 103, 104, 98, 103.5, 30),
    ]


def test_specific_features_are_causal_and_stable():
    bars = _bars()
    features = extract_specific_features(bars, window=3)
    assert len(features) == len(bars)
    assert features[0]["vpa_price_change"] == 0
    assert features[2]["vsa_volume_expansion"] == 12 / 11
    # At i=3 the causal 3-bar volume SMA is (11+12+30)/3 only after inclusion;
    # the implementation's trailing window is (11+12+30), so expansion is 30/SMA.
    assert abs(features[3]["vsa_volume_expansion"] - (30 / ((11 + 12 + 30) / 3))) < 1e-12
    assert "wyckoff_spring_proxy" in features[3]
    assert "wyckoff_upthrust_proxy" in features[3]


def test_high_volume_wide_spread_creates_expansion_proxies():
    features = extract_specific_features(_bars(), window=3)
    f = features[3]
    assert f["vsa_volume_expansion"] > 1.5
    assert f["vpa_volume_price_expansion"] is True
    assert f["wyckoff_sos_proxy"] is True


def test_zero_range_is_safe():
    b = MarketBar(datetime(2026, 1, 1, tzinfo=timezone.utc), 100, 100, 100, 100, 10)
    f = extract_specific_features([b])[0]
    assert f["vsa_wide_spread"] == 0
    assert f["vsa_effort_result"] is None
