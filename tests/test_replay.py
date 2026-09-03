from engine.replay import replay


def test_long_round_trip_is_deterministic():
    trades = [
        {"timestamp": "2026-01-01T00:00:00Z", "side": "buy", "symbol": "BTCUSDT", "price": 100, "quantity": 10, "id": 1},
        {"timestamp": "2026-01-01T01:00:00Z", "side": "sell", "symbol": "BTCUSDT", "price": 110, "quantity": 10, "id": 2},
    ]
    a = replay(trades, starting_cash=1000)
    b = replay(trades, starting_cash=1000)
    assert a == b
    assert a["ending_value"] == 1100
    assert a["return_pct"] == 10.0


def test_oversell_fails_closed():
    result = replay([
        {"timestamp": "1", "side": "sell", "symbol": "BTCUSDT", "price": 100, "quantity": 1, "id": 1},
    ])
    assert result["rejected"][0]["reason"] == "sell_exceeds_long"
    assert result["accepted_trade_count"] == 0


def test_short_cover_round_trip():
    result = replay([
        {"timestamp": "1", "side": "short", "symbol": "BTCUSDT", "price": 100, "quantity": 2, "id": 1},
        {"timestamp": "2", "side": "cover", "symbol": "BTCUSDT", "price": 90, "quantity": 2, "id": 2},
    ], starting_cash=1000)
    assert result["ending_value"] == 1020
    assert result["positions"] == {}


def test_ordering_is_timestamp_then_trade_id():
    result = replay([
        {"timestamp": "2", "side": "sell", "symbol": "BTCUSDT", "price": 110, "quantity": 1, "id": 2},
        {"timestamp": "1", "side": "buy", "symbol": "BTCUSDT", "price": 100, "quantity": 1, "id": 1},
    ], starting_cash=1000)
    assert result["ending_value"] == 1010
