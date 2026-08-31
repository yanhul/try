import csv
import math

from engine.events import MarketBar
from engine.strategy import ReferenceStrategy
from engine.ledger import build_ledger
from engine.execution import execute_trades
from engine.risk_exit import FixedRiskRewardExit
from engine.walk_forward import generate_walk_forward

DATA = "data/BTCUSDT_1h.csv"
TRAIN = 1100
TEST = 500
STEP = 500

# This is a pre-declared decision gate, not an optimizer.
# Replace the strategy only after the current fixed specification fails all
# robustness gates on an expanded, genuinely unseen OOS sample.
MIN_OOS_TRADES = 60


def load_bars():
    with open(DATA, newline="", encoding="utf-8-sig") as f:
        return [MarketBar(timestamp=r["timestamp"], open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"])) for r in csv.DictReader(f)]


def collect():
    bars = load_bars()
    events = ReferenceStrategy().process(bars)
    ledger = build_ledger(events)
    exit_policy = FixedRiskRewardExit(0.01, 2.0)
    windows = generate_walk_forward(len(bars), TRAIN, TEST, STEP)
    rows = []
    for n, w in enumerate(windows):
        test_ledger = [t for t in ledger if w.test_start <= t.entry_bar < w.test_end]
        executed, skipped = execute_trades(bars, test_ledger, exit_policy, max_concurrent=1)
        for x in executed:
            t = x.ledger_trade
            e, p = t.entry_price, x.exit.price
            r = (p / e - 1.0) if t.direction.value == "bullish" else (e / p - 1.0)
            rows.append((n, x.exit.bar_index, r))
    return rows


def main():
    bars = load_bars()
    windows = generate_walk_forward(len(bars), TRAIN, TEST, STEP)
    rows = collect()
    returns = [r for _, _, r in rows]
    total = sum(returns)
    compound = math.prod(1.0 + r for r in returns) - 1.0 if returns else 0.0
    print("DATA_BARS", len(bars))
    print("WF_WINDOWS", len(windows))
    print("OOS_TRADES", len(rows))
    print("OOS_TOTAL_RETURN", total)
    print("OOS_COMPOUND_RETURN", compound)
    print("DECISION_GATE", {"minimum_oos_trades": MIN_OOS_TRADES, "enough_data_for_replacement_decision": len(rows) >= MIN_OOS_TRADES})
    if len(rows) < MIN_OOS_TRADES:
        print("DECISION", "DO_NOT_REPLACE_YET")
        print("REASON", "OOS sample is too small for the pre-declared replacement gate")
    else:
        print("DECISION", "REVIEW_ROBUSTNESS_GATES")


if __name__ == "__main__":
    main()
