from research.btc_translation_policy import btc_translation_status, eligible_survivors


def source(family, market=None, title="", description=""):
    return {"family": family, "market": market, "title": title, "description": description, "source_url": "https://example.test/source"}


def test_rejects_cross_sectional_and_equity_sources_for_btc():
    ok, reason = btc_translation_status(source("cross_sectional", None, "factor portfolio", "cross-sectional alpha portfolio"))
    assert not ok
    assert reason.startswith("non_portable_family:")
    ok, reason = btc_translation_status(source("mean_reversion", "CN_A_SHARE", "A-share factor", "China stock factor portfolio"))
    assert not ok
    assert "requires_unavailable_data" in reason or "single_asset_incompatible" in reason


def test_rejects_order_book_lane_even_if_misclassified_as_smc():
    ok, reason = btc_translation_status(source("smc_ict", None, "order book", "Level-2 order book liquidity strategy"))
    assert not ok
    assert reason.startswith("requires_unavailable_data:")


def test_accepts_portable_crypto_ohlcv_mechanism():
    ok, reason = btc_translation_status(source("mean_reversion", None, "Crypto mean reversion", "crypto z-score mean reversion strategy"))
    assert ok
    assert reason == "portable_to_btc_ohlcv"


def test_filter_preserves_only_btc_compatible_sources():
    eligible, rejected = eligible_survivors([
        source("smc_ict", None, "BTC/ETH ICT", "crypto liquidity sweep MSS FVG"),
        source("china_a_share", "CN_A_SHARE", "A-share", "China stock portfolio"),
    ])
    assert len(eligible) == 1
    assert len(rejected) == 1
    assert eligible[0]["family"] == "smc_ict"
