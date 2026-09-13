from dataclasses import dataclass

from .events import Direction, EventType, Event


@dataclass(frozen=True)
class LedgerTrade:
    direction: Direction
    sweep_bar: int
    mss_bar: int
    fvg_bar: int
    entry_bar: int
    entry_price: float


def build_ledger(events: list[Event]) -> list[LedgerTrade]:
    state: dict[Direction, dict[str, Event]] = {}
    trades: list[LedgerTrade] = []

    for event in events:
        d = event.direction

        if event.event_type == EventType.LIQUIDITY_SWEEP:
            state[d] = {"sweep": event}

        elif event.event_type == EventType.MSS:
            if (
                d in state
                and event.bar_index > state[d]["sweep"].bar_index
            ):
                state[d] = {
                    "sweep": state[d]["sweep"],
                    "mss": event,
                }

        elif event.event_type == EventType.FVG:
            if (
                d in state
                and "mss" in state[d]
                and event.bar_index > state[d]["mss"].bar_index
            ):
                state[d]["fvg"] = event

        elif event.event_type == EventType.RETEST:
            if (
                d in state
                and "mss" in state[d]
                and "fvg" in state[d]
            ):
                s = state[d]
                sweep_bar = s["sweep"].bar_index
                mss_bar = s["mss"].bar_index
                fvg_bar = s["fvg"].bar_index
                entry_bar = event.bar_index

                # Defensive lineage gate: malformed externally supplied
                # events must never become executable ledger trades.
                if not (sweep_bar < mss_bar < fvg_bar < entry_bar):
                    state.pop(d, None)
                    continue

                trades.append(
                    LedgerTrade(
                        direction=d,
                        sweep_bar=sweep_bar,
                        mss_bar=mss_bar,
                        fvg_bar=fvg_bar,
                        entry_bar=entry_bar,
                        entry_price=event.price,
                    )
                )

                state.pop(d, None)

    return trades
