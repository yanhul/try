from datetime import datetime, timedelta, timezone

import pytest

from engine.context_features import PnFConfig, gann_reference, point_figure_columns, rolling_volatility, volume_profile, vwap
from engine.events import MarketBar


def _bars():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = [100.0, 101.0, 102.0, 100.0, 103.0]
    return [MarketBar(start + timedelta(hours=i), c, c + 1, c - 1, c, 10 + i) for i, c in enumerate(closes)]


def test_vwap_and_volatility_are_causal():
    bars = _bars()
    v = vwap(bars)
    vol = rolling_volatility(bars, window=3)
    assert len(v) == len(bars)
    assert v[0] == pytest.approx(100.0)
    assert vol[0] is None
    assert vol[-1] is not None


def test_volume_profile_has_deterministic_poc():
    profile = volume_profile(_bars(), bins=4)
    assert profile["poc"] is not None
    assert len(profile["bins"]) == 4


def test_pnf_is_deterministic_and_validates_config():
    cols = point_figure_columns(_bars(), PnFConfig(box_size=1.0, reversal=3))
    assert cols
    with pytest.raises(ValueError):
        point_figure_columns(_bars(), PnFConfig(box_size=0))


def test_gann_reference_is_causal():
    refs = gann_reference(_bars(), lookback=3)
    assert refs[0]["elapsed"] == 0.0
    assert refs[-1]["anchor"] == 102.0
