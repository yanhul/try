# BC1 Evaluation Rerun Status

Status: NEED RERUN

Research-grade walk-forward evaluation is now guarded by minimum evidence requirements: 500 test bars per window, 5 windows, and 2,500 cumulative test bars.

The reference strategy and BC1 baseline remain unchanged.

Run `python run_bc1_research_wf.py` and then `python -m pytest -q` before interpreting robustness results.
