from engine.parity import ParityEvent, compare_events


def event(
    timestamp="2026-01-01T00:00:00+00:00",
    bar_index=1,
    event_type="LIQUIDITY_SWEEP",
    direction="bullish",
    price=95.0,
):
    return ParityEvent(
        timestamp,
        bar_index,
        event_type,
        direction,
        price,
    )


def test_identical_events_match():
    e = event()

    assert compare_events([e], [e]) == []


def test_bar_index_mismatch_is_reported():
    reference = event(bar_index=10)
    candidate = event(bar_index=11)

    differences = compare_events([reference], [candidate])

    assert any(
        d["field"] == "bar_index"
        for d in differences
    )


def test_event_type_mismatch_is_reported():
    reference = event(event_type="MSS")
    candidate = event(event_type="FVG")

    differences = compare_events([reference], [candidate])

    assert any(
        d["field"] == "event_type"
        for d in differences
    )


def test_direction_mismatch_is_reported():
    reference = event(direction="bullish")
    candidate = event(direction="bearish")

    differences = compare_events([reference], [candidate])

    assert any(
        d["field"] == "direction"
        for d in differences
    )


def test_price_tolerance_is_respected():
    reference = event(price=100.0)
    candidate = event(price=100.0001)

    assert compare_events(
        [reference],
        [candidate],
        price_tolerance=0.001,
    ) == []


def test_missing_event_is_reported():
    differences = compare_events(
        [event()],
        [],
    )

    assert differences[0]["type"] == "MISSING_CANDIDATE_EVENT"


def test_extra_event_is_reported():
    differences = compare_events(
        [],
        [event()],
    )

    assert differences[0]["type"] == "EXTRA_CANDIDATE_EVENT"


def test_multiple_differences_are_not_collapsed():
    reference = event(
        bar_index=10,
        event_type="MSS",
        direction="bullish",
        price=100.0,
    )

    candidate = event(
        bar_index=11,
        event_type="FVG",
        direction="bearish",
        price=101.0,
    )

    differences = compare_events(
        [reference],
        [candidate],
    )

    fields = {d["field"] for d in differences}

    assert {
        "bar_index",
        "event_type",
        "direction",
        "price",
    }.issubset(fields)
