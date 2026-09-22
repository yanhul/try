from datetime import datetime, timedelta, timezone
import json
from engine.research_pipeline import run_is_validation_oos


def _csv(path):
    rows = ["timestamp,open,high,low,close,volume"]
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(90):
        # Enough movement for the reference strategy to produce events/trades.
        p = 100 + ((i % 10) * 3) + (i // 10)
        ts = start + timedelta(hours=i)
        rows.append(f"{ts.isoformat()},{p},{p+4},{p-4},{p},10")
    path.write_text("\n".join(rows), encoding="utf-8")


def test_pipeline_has_strict_stage_order(tmp_path):
    csv = tmp_path / "data.csv"
    _csv(csv)
    out = tmp_path / "pipeline.json"
    candidates = [
        {"stop_fraction": 0.01, "reward_multiple": 1.0},
        {"stop_fraction": 0.02, "reward_multiple": 2.0},
    ]
    result = run_is_validation_oos(csv, out, candidates)
    assert result["protocol"]["selection"] == "IS_only"
    assert result["protocol"]["validation"] == "gate_only"
    assert result["protocol"]["oos"] == "locked_single_evaluation"
    assert result["candidate_count"] == 2
    assert result["dataset"]["sha256"]
    assert out.exists()


def test_failed_validation_blocks_oos(tmp_path):
    csv = tmp_path / "data.csv"
    _csv(csv)
    result = run_is_validation_oos(
        csv, tmp_path / "blocked.json",
        [{"stop_fraction": 0.01, "reward_multiple": 1.0}],
        validation_min_profit_factor=999.0,
    )
    assert result["validation"]["passed"] is False
    assert result["oos"] is None


def test_split_cache_preserves_causal_event_warmup(tmp_path):
    from engine.backtest import load_bars
    from engine.data_split import chronological_split
    from engine.ledger import build_ledger
    from engine.strategy import ReferenceStrategy
    from engine.split_research import run_split

    csv = tmp_path / "data.csv"
    _csv(csv)
    bars = load_bars(csv)
    splits = chronological_split(len(bars))
    events = ReferenceStrategy().process(bars)
    ledger = build_ledger(events)
    context = {
        "bars": bars,
        "events": events,
        "ledger": ledger,
        "split_cache": {
            (splits[1].start, splits[1].end): {
                "events": [e for e in events if e.bar_index < splits[1].end],
                "ledger": [t for t in ledger if splits[1].start <= t.entry_bar < splits[1].end],
            }
        },
    }
    uncached = run_split(
        bars, splits[1].start, splits[1].end, 0.01, 2.0, 0.0,
        {"stop_fraction": 0.01, "reward_multiple": 2.0},
    )
    cached = run_split(
        bars, splits[1].start, splits[1].end, 0.01, 2.0, 0.0,
        {"stop_fraction": 0.01, "reward_multiple": 2.0},
        research_context=context,
    )
    assert cached == uncached
