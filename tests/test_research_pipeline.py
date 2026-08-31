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
