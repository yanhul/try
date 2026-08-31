# BC1 Evaluation Guard

## Purpose

This guard separates exploratory walk-forward tests from evidence suitable for a robustness claim. It does not alter the reference strategy.

## Research-grade minimum

- test window: at least 500 bars
- at least 5 walk-forward windows
- at least 2,500 cumulative test bars
- train/test/step must be positive and fit inside the dataset

For the committed BTCUSDT 1h dataset (3,624 bars), one concrete configuration that satisfies these minima is:

- train: 1,100 bars
- test: 500 bars
- step: 500 bars
- resulting windows: 5

This configuration is an evaluation configuration, not a claimed optimal parameter set. It must be rerun and its results independently inspected before any robustness conclusion is made.

## Interpretation rule

The existing 15-bar walk-forward artifact is retained as historical evidence/debug output but must not be used to claim robustness. The existing two-window result is also insufficient on its own for a robustness claim.
