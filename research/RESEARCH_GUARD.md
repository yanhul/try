# Research Guard

- Validated datasets are immutable; record SHA-256.
- Every experiment records hypothesis and config.
- OOS is read-only and excluded from parameter search.
- Regression/parity failures block experiments.
- Never delete losing trades or alter timestamps to improve metrics.
- Preserve stdout/stderr for reproducibility.
