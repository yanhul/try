from engine.hypotheses import HYPOTHESES


def ctx(vr=2.0, loc=0.9, rr=2.0):
    row = {"volume_ratio": vr, "close_location": loc, "range_ratio": rr}
    return {"sweep": row, "mss": row, "fvg": row, "entry": row}


def test_hypotheses_are_pre_registered():
    assert list(HYPOTHESES) == ["baseline", "sweep_confirmation", "sweep_wide_effort", "quiet_retest"]
    assert HYPOTHESES["baseline"](ctx(), "bullish")
    assert HYPOTHESES["sweep_confirmation"](ctx(), "bullish")
    assert HYPOTHESES["sweep_confirmation"](ctx(), "bearish") is False
    assert HYPOTHESES["sweep_wide_effort"](ctx(), "bullish")


def test_quiet_retest_requires_low_effort():
    assert HYPOTHESES["quiet_retest"](ctx(vr=0.8, rr=1.0), "bullish")
    assert not HYPOTHESES["quiet_retest"](ctx(vr=1.0, rr=1.0), "bullish")
    assert not HYPOTHESES["quiet_retest"](ctx(vr=0.8, rr=1.1), "bullish")
