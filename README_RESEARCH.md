# AI Trading Research Runner

This is an independent Python reference backtester for the V1.1 research baseline.
It is intentionally conservative and is **not** a live-trading system.

## Data
CSV columns required: `timestamp,open,high,low,close,volume`.
Timestamp should be parseable as UTC.

## Run
```bash
python -m engine.backtest data/BTCUSDT.csv --out research/results.json
```

## AI loop
1. AI proposes one hypothesis.
2. Run on IS only.
3. Save immutable experiment config + result.
4. Run regression tests.
5. Freeze the hypothesis.
6. Evaluate once on locked validation/OOS data.
7. Never feed OOS metrics back into optimization.

The Python engine is a research/reference implementation. Before using results to claim parity with TradingView, compare event-by-event exports from the Pine strategy.

## Base execution contract (v1.2.1)

The reference engine uses a deterministic, single-position execution model:

- The ledger `entry_price` is the execution price; it is never replaced by a later bar close.
- Stop/target fills occur at the actual level when an intrabar touch is observable.
- If a bar opens through a stop/target, the fill is the bar open (gap-through handling).
- If stop and target are both touched in one OHLC bar, stop wins because OHLC does not reveal intrabar order.
- If neither level is reached before the dataset/split ends, the final close is a `time` exit.
- Overlapping entries are skipped under `max_concurrent=1`; the engine does not silently assume unlimited capital.
- Proportional transaction costs are explicit through `round_trip_cost`; the default is zero and must not be interpreted as a claim about live costs.
- Split research uses causal history up to each split end instead of resetting the strategy at the split boundary. Executions are still required to enter and exit inside the split.
- Every research result records the input CSV SHA-256.

The result files produced before this contract was introduced should be treated as historical/non-comparable until regenerated.

## BC1 — Pre-registered Volume/Price Hypotheses

The repository now contains a separate hypothesis layer (`engine/hypotheses.py`)
and runner (`run_hypothesis_research.py`). It evaluates fixed, measurable
proxies using the same ledger/execution/metrics stack as the reference baseline.

Research handles are deliberately descriptive, not claims of canonical Wyckoff
or VSA labels:

- `sweep_confirmation`: elevated volume and directional close on the sweep bar.
- `sweep_wide_effort`: elevated volume + wide spread + directional close on the sweep bar.
- `quiet_retest`: below-average volume + non-wide spread on the retest bar.

No thresholds are optimized in this layer. Validation is a gate; OOS is only
reported after a validation pass and is never used for selection. Because four
fixed hypotheses are evaluated, a validation pass is not proof of an edge; it
is a hypothesis-generation result that requires further independent data.
