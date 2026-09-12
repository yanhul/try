# TradingView Screener adapter

`engine/tv_screener_adapter.py` adds an optional adapter around `deepentropy/tvscreener`.

## Boundary

TradingView Screener is **universe discovery only**. Its snapshot is not authoritative
historical market data and must not be used directly as backtest truth, IS/OOS evidence,
or promotion evidence.

Pipeline:

```text
TradingView Screener
        |
        v
raw external snapshot
        |
        v
provenance + integrity validation
        |
        v
canonical dataset / Parquet
        |
        v
Reference Engine -> experiments -> IS -> validation -> OOS LOCKED
```

The adapter deliberately keeps the dependency optional. Install only when the discovery
stage is enabled:

```bash
pip install tvscreener pandas
```

The adapter exposes:

- `screen_crypto(...)` for bounded crypto universe discovery.
- `snapshot_metadata(...)` for fetch-time/provenance metadata.
- `symbols_from_snapshot(...)` for candidate extraction with stable de-duplication.

Do not import TradingView data into the authoritative backtest path without a separate
integrity/provenance step. The upstream project itself describes the library as an
unofficial third-party TradingView interface.
