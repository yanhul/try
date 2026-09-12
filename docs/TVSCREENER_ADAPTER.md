# TradingView Screener adapter

`engine/tv_screener_adapter.py` is the external discovery adapter. It is connected to `engine/universe_discovery.py`, which creates a timestamped and SHA-256 fingerprinted candidate-universe snapshot.

## Flow

```text
TradingView / tvscreener
        -> tv_screener_adapter
        -> universe_discovery
        -> raw JSON snapshot + provenance + hash
        -> resolve candidates against authoritative OHLCV source
        -> data integrity validation
        -> canonical dataset
        -> backtest / IS / validation / OOS
```

The TradingView snapshot is **not** historical truth and must not be passed directly to the backtest engine. `verify_snapshot()` fails closed if the persisted payload has changed.

## Run

Install the optional external dependency:

```bash
pip install tvscreener pandas
```

Then:

```bash
python tools/discover_crypto_universe.py --limit 100 --out data/universe/tradingview_crypto.json
```

The output contains the raw screener rows, provenance, candidate symbols, and a SHA-256 payload fingerprint.

The authoritative price path remains the existing downloader/data validator. The existing validator enforces timestamp, OHLCV, ordering, and optional cadence checks; TradingView discovery does not bypass those checks.
