# BC1 Evaluation Status

Status: **NEED RERUN**

The evaluation layer now rejects research-grade walk-forward configurations with fewer than 500 test bars, fewer than 5 windows, or fewer than 2,500 cumulative test bars.

The reference strategy, execution model, and BC1 baseline branch are unchanged.

Required next run:

```powershell
python run_bc1_research_wf.py
python -m pytest -q
```

Do not interpret the generated research-grade walk-forward output as evidence of edge until the rerun completes and the resulting test-window metrics are inspected.
