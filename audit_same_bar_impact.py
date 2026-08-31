#!/usr/bin/env python3
from collections import Counter, defaultdict

from engine.backtest import load_bars
from engine.strategy import ReferenceStrategy


def main() -> None:
    bars = load_bars("data/BTCUSDT_1h.csv")
    events = ReferenceStrategy().process(bars)

    by_bar = defaultdict(list)
    for event in events:
        by_bar[event.bar_index].append(event.event_type.value)

    same_bar_sweep_mss = [
        i for i, types in by_bar.items()
        if "LIQUIDITY_SWEEP" in types and "MSS" in types
    ]

    same_bar_sequences = Counter(
        tuple(sorted(types)) for i, types in by_bar.items() if len(types) > 1
    )

    retests = [e for e in events if e.event_type.value == "RETEST"]
    retest_after_same_bar = 0
    for retest in retests:
        prior_same = [i for i in same_bar_sweep_mss if i < retest.bar_index]
        if prior_same:
            retest_after_same_bar += 1

    print("BARS", len(bars))
    print("EVENTS", len(events))
    print("SAME_BAR_SWEEP_MSS", len(same_bar_sweep_mss))
    print("SAME_BAR_SWEEP_MSS_RATE_OF_SWEEPS", len(same_bar_sweep_mss) / sum(1 for e in events if e.event_type.value == "LIQUIDITY_SWEEP"))
    print("MULTI_EVENT_BAR_PATTERNS", dict(same_bar_sequences))
    print("RETESTS_AFTER_ANY_SAME_BAR_SWEEP_MSS", retest_after_same_bar)


if __name__ == "__main__":
    main()
