from datetime import datetime, timedelta, timezone

import pytest

from engine.context_features import (
    PnFConfig,
    gann_reference,
    point_figure_columns,
    point_figure_directions,
    rolling_volatility,
    rolling_volume_profile_poc,
    volume_profile,
    vwap,
)
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


def test_rolling_volume_profile_is_causal():
    bars = _bars()
    future = bars + [MarketBar(bars[-1].timestamp + timedelta(hours=1), 250.0, 251.0, 249.0, 250.0, 1000.0)]
    before = rolling_volume_profile_poc(bars, window=3, bins=4)
    after = rolling_volume_profile_poc(future, window=3, bins=4)
    assert after[:len(bars)] == before


def test_pnf_is_deterministic_and_validates_config():
    cols = point_figure_columns(_bars(), PnFConfig(box_size=1.0, reversal=3))
    assert cols
    with pytest.raises(ValueError):
        point_figure_columns(_bars(), PnFConfig(box_size=0))


def test_streaming_pnf_matches_prefix_columns_and_is_causal():
    bars = _bars()
    config = PnFConfig(box_size=1.0, reversal=3)
    directions = point_figure_directions(bars, config)
    expected = []
    for i in range(len(bars)):
        cols = point_figure_columns(bars[:i + 1], config)
        expected.append(cols[-1]["direction"] if cols else None)
    assert directions == expected

    future = bars + [MarketBar(bars[-1].timestamp + timedelta(hours=1), 250.0, 251.0, 249.0, 250.0, 1000.0)]
    assert point_figure_directions(future, config)[:len(bars)] == directions


def test_gann_reference_is_causal():
    refs = gann_reference(_bars(), lookback=3)
    assert refs[0]["elapsed"] == 0.0
    assert refs[-1]["anchor"] == 102.0
