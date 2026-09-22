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
introduced as explicit hypotheses and tested through the IS -> validation -> OOS
protocol rather than being treated as established edge.

### Long-running research execution

Research jobs should be submitted asynchronously when the execution runtime
supports completion events.

Preferred flow:

`submit -> persist job/attempt identity -> suspend -> completion event -> resume -> verify -> continue`

Avoid using repeated `sleep`/status polling as the default waiting mechanism.
Polling is only a fallback when no completion event exists, and it must be
bounded by timeout and execution budget.

This is a harness-efficiency rule, not a profitability claim. Any claimed
cost/time reduction must be measured with a controlled before/after benchmark
on the same research workload.
