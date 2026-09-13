from datetime import datetime, timezone, timedelta

from engine.events import MarketBar
from engine.trading_features import family_features


def _bars(n=40):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        MarketBar(start + timedelta(hours=i), 100+i, 101+i, 99+i, 100.5+i, 1000+i)
        for i in range(n)
    ]


def test_family_features_are_causal_and_complete_for_ohlcv_lane():
    bars = _bars()
    features = family_features(bars, pnf_box_size=0.5)
    expected = {
        "momentum_trend", "mean_reversion", "volatility", "smc_ict_events",
        "fvg_imbalance_events", "wyckoff_vsa_vpa", "vwap_volume_profile",
        "regime_proxy", "seasonality", "point_figure", "gann_reference",
    }
    assert expected <= features.keys()
    assert len(features["momentum_trend"]) == len(bars)
    assert len(features["volatility"]) == len(bars)
    assert len(features["vwap_volume_profile"]["vwap"]) == len(bars)
    assert len(features["regime_proxy"]) == len(bars)
    assert len(features["point_figure"]) == len(bars)
    assert len(features["gann_reference"]) == len(bars)
