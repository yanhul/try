import hashlib
import json
from pathlib import Path

from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .execution import execute_trades
from .ledger import build_ledger
from .metrics import Trade, calculate_metrics
from .risk_exit import FixedRiskRewardExit
from .strategy import ReferenceStrategy
from .strategy_spec import canonicalize, provenance, strategy_hash
from .feature_library import evaluate_filters


def _sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_split(
    bars,
    start,
    end,
    stop_fraction=0.01,
    reward_multiple=2.0,
    round_trip_cost=0.0,
    strategy_spec=None,
):
    if end <= start:
        return {"bars": 0, "events": 0, "trades": 0, "metrics": {}}

    spec = canonicalize(strategy_spec or {"strategy_id": "ReferenceStrategy"})
    filters = spec.get("features", {}).get("filters", {})

    # Warm-up is causal: strategy sees only bars before `end`. We filter
    # executions by entry timestamp so split boundaries do not reset state.
    history = bars[:end]
    events = ReferenceStrategy().process(history)
    ledger = [t for t in build_ledger(events) if start <= t.entry_bar < end]
    if filters:
        ledger = [t for t in ledger if evaluate_filters(history, t.entry_bar, filters)]
    exit_policy = FixedRiskRewardExit(stop_fraction, reward_multiple)
    executed, skipped_overlap = execute_trades(history, ledger, exit_policy)

    executed = [x for x in executed if x.exit.bar_index < end]
    trades = [
        Trade(
            entry=x.ledger_trade.entry_price,
            exit=x.exit.price,
            direction=x.ledger_trade.direction.value,
            entry_bar=x.ledger_trade.entry_bar,
            exit_bar=x.exit.bar_index,
            exit_reason=x.exit.reason,
        )
        for x in executed
    ]

    return {
        "bars": end - start,
        "events": sum(1 for e in events if start <= e.bar_index < end),
        "trades": len(trades),
        "skipped_overlap_trades": skipped_overlap,
        "metrics": calculate_metrics(trades, round_trip_cost),
        "strategy_hash": strategy_hash(spec),
    }


def run_split_research(csv_path, output_path, stop_fraction=0.01, reward_multiple=2.0, round_trip_cost=0.0, strategy_spec=None):
    bars = load_bars(csv_path)
    splits = chronological_split(len(bars))
    validate_splits(splits, len(bars))
    spec = canonicalize(strategy_spec or {"strategy_id": "ReferenceStrategy"})

    result = {
        "schema_version": 3,
        "dataset": {"bars": len(bars), "sha256": _sha256(csv_path)},
        "strategy": provenance(spec),
        "parameters": {
            "stop_fraction": stop_fraction,
            "reward_multiple": reward_multiple,
        },
        "execution": {
            "round_trip_cost": round_trip_cost,
            "max_concurrent": 1,
            "overlap_policy": "skip_until_flat",
            "split_warmup": "causal_history_before_split_end",
        },
        "dataset_bars": len(bars),
        "splits": {
            s.name: run_split(bars, s.start, s.end, stop_fraction, reward_multiple, round_trip_cost, spec)
            for s in splits
        },
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
