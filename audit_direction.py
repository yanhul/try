from engine.backtest import load_bars
from engine.data_split import chronological_split
from engine.ledger import build_ledger
from engine.metrics import Trade, calculate_metrics
from engine.risk_exit import FixedRiskRewardExit
from engine.strategy import ReferenceStrategy

bars = load_bars("data/BTCUSDT_1h.csv")
splits = chronological_split(len(bars))

def evaluate(segment):
    events = ReferenceStrategy().process(segment)
    ledger = build_ledger(events)

    exit_policy = FixedRiskRewardExit(
        stop_fraction=0.015,
        reward_multiple=1.5,
    )

    groups = {
        "bullish": [],
        "bearish": [],
    }

    for item in ledger:
        if item.entry_bar >= len(segment):
            continue

        exit_bar = exit_policy.exit_bar(segment, item)

        if exit_bar <= item.entry_bar:
            continue

        groups[item.direction.value].append(
            Trade(
                entry=segment[item.entry_bar].close,
                exit=segment[exit_bar].close,
                direction=item.direction.value,
            )
        )

    return groups

for split in splits:
    segment = bars[split.start:split.end]
    groups = evaluate(segment)

    print(f"\n=== {split.name} ===")

    for direction in ("bullish", "bearish"):
        trades = groups[direction]
        metrics = calculate_metrics(trades)

        print(direction.upper())
        print("  trades:", len(trades))
        print("  wins:", metrics["win_count"])
        print("  losses:", metrics["loss_count"])
        print("  win_rate:", round(metrics["win_rate"], 4))
        pf = metrics["profit_factor"]
        if pf is None:
            print("  PF: N/A (no losing trades)")
        else:
            print("  PF:", round(pf, 4))
        print("  return:", round(metrics["total_return"], 6))
        print("  DD:", round(metrics["max_drawdown"], 6))
