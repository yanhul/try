# Trading Research V1.1

Baseline research package: Liquidity Sweep -> MSS -> FVG -> Retest.

The Python tests verify event ordering only. They are not a market backtest and make no profitability claim.

Next: implement a Python OHLCV reference engine, parity-check it against TradingView, then add Wyckoff/VSA/VPA as a separate feature layer and evaluate with IS/validation/OOS + walk-forward.

## Research protocol v1.2

The research path is now explicitly separated into:

1. **IS** — candidate selection only.
2. **Validation** — pass/fail gate only; never used to rank candidates.
3. **OOS** — locked single evaluation after validation passes; OOS is not fed back into search.

Run it with:

```bash
python run_research_pipeline.py \
  --data data/BTCUSDT_1h.csv \
  --candidates research/candidates_v1.json \
  --out research/BTCUSDT_1h_IS_VAL_OOS_v1.json
```

### Feature layer

`engine/features.py` contains causal, measurable OHLCV features (spread, body,
wicks, close location, volume/range ratios, effort/result, and one-bar structure).
It is deliberately **not** a Wyckoff/VSA/VPA classifier. Those labels must be
introduced as explicit hypotheses and tested through the IS → validation → OOS
protocol rather than being treated as established edge.
