import hashlib
import json
from pathlib import Path

from .backtest import load_bars
from .execution import execute_trades
from .ledger import build_ledger
from .metrics import Trade, calculate_metrics
from .risk_exit import FixedRiskRewardExit
from .strategy import ReferenceStrategy


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_research(
    csv_path,
    output_path,
    stop_fraction=0.01,
    reward_multiple=2.0,
    round_trip_cost=0.0,
):
    bars = load_bars(csv_path)
    if not bars:
        raise ValueError("empty dataset")

    events = ReferenceStrategy().process(bars)
    ledger = build_ledger(events)
    exit_policy = FixedRiskRewardExit(stop_fraction, reward_multiple)
    executed, skipped_overlap = execute_trades(bars, ledger, exit_policy)

    trades = [
        Trade(
            entry=item.ledger_trade.entry_price,
            exit=item.exit.price,
            direction=item.ledger_trade.direction.value,
            entry_bar=item.ledger_trade.entry_bar,
            exit_bar=item.exit.bar_index,
            exit_reason=item.exit.reason,
        )
        for item in executed
    ]

    metrics = calculate_metrics(trades, round_trip_cost)
    result = {
        "schema_version": 2,
        "data": {
            "file": str(Path(csv_path).resolve()),
            "sha256": _sha256(csv_path),
            "bars": len(bars),
            "start": bars[0].timestamp.isoformat(),
            "end": bars[-1].timestamp.isoformat(),
        },
        "parameters": {
            "stop_fraction": stop_fraction,
            "reward_multiple": reward_multiple,
        },
        "execution": {
            "round_trip_cost": round_trip_cost,
            "max_concurrent": 1,
            "overlap_policy": "skip_until_flat",
        },
        "bars": len(bars),
        "events": len(events),
        "ledger_trades": len(ledger),
        "evaluated_trades": len(trades),
        "skipped_overlap_trades": skipped_overlap,
        "metrics": metrics,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
