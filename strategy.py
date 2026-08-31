from dataclasses import dataclass
from typing import Optional

from .events import Direction, Event, EventType, MarketBar


@dataclass(frozen=True)
class FVGZone:
    direction: Direction
    created_at: int
    lower: float
    upper: float


class ReferenceStrategy:
    def __init__(self):
        self.reset()

    def reset(self):
        self.events = []
        self._sweep: Optional[Event] = None
        self._fvg: Optional[FVGZone] = None

    def process(self, bars: list[MarketBar]) -> list[Event]:
        self.reset()

        for i in range(len(bars)):
            bar = bars[i]

            # ------------------------------------------------
            # Liquidity sweep
            # ------------------------------------------------
            if i >= 1:
                prev = bars[i - 1]

                if bar.low < prev.low and bar.close > prev.low:
                    event = Event(
                        timestamp=bar.timestamp,
                        bar_index=i,
                        event_type=EventType.LIQUIDITY_SWEEP,
                        direction=Direction.BULLISH,
                        price=prev.low,
                    )
                    self.events.append(event)
                    self._sweep = event

                elif bar.high > prev.high and bar.close < prev.high:
                    event = Event(
                        timestamp=bar.timestamp,
                        bar_index=i,
                        event_type=EventType.LIQUIDITY_SWEEP,
                        direction=Direction.BEARISH,
                        price=prev.high,
                    )
                    self.events.append(event)
                    self._sweep = event

            # ------------------------------------------------
            # MSS
            # ------------------------------------------------
            if self._sweep is not None and i >= 1:
                prev = bars[i - 1]

                if (
                    self._sweep.direction == Direction.BULLISH
                    and bar.close > prev.high
                ):
                    event = Event(
                        timestamp=bar.timestamp,
                        bar_index=i,
                        event_type=EventType.MSS,
                        direction=Direction.BULLISH,
                        price=prev.high,
                    )
                    self.events.append(event)
                    self._sweep = event

                elif (
                    self._sweep.direction == Direction.BEARISH
                    and bar.close < prev.low
                ):
                    event = Event(
                        timestamp=bar.timestamp,
                        bar_index=i,
                        event_type=EventType.MSS,
                        direction=Direction.BEARISH,
                        price=prev.low,
                    )
                    self.events.append(event)
                    self._sweep = event

            # ------------------------------------------------
            # FVG
            # ------------------------------------------------
            if i >= 2 and self._sweep is not None:
                left = bars[i - 2]

                if (
                    self._sweep.event_type == EventType.MSS
                    and self._sweep.direction == Direction.BULLISH
                    and bar.low > left.high
                ):
                    zone = FVGZone(
                        direction=Direction.BULLISH,
                        created_at=i,
                        lower=left.high,
                        upper=bar.low,
                    )
                    self._fvg = zone

                    self.events.append(
                        Event(
                            timestamp=bar.timestamp,
                            bar_index=i,
                            event_type=EventType.FVG,
                            direction=Direction.BULLISH,
                            price=zone.lower,
                        )
                    )

                elif (
                    self._sweep.event_type == EventType.MSS
                    and self._sweep.direction == Direction.BEARISH
                    and bar.high < left.low
                ):
                    zone = FVGZone(
                        direction=Direction.BEARISH,
                        created_at=i,
                        lower=bar.high,
                        upper=left.low,
                    )
                    self._fvg = zone

                    self.events.append(
                        Event(
                            timestamp=bar.timestamp,
                            bar_index=i,
                            event_type=EventType.FVG,
                            direction=Direction.BEARISH,
                            price=zone.upper,
                        )
                    )

            # ------------------------------------------------
            # Retest
            # ------------------------------------------------
            if self._fvg is not None and i > self._fvg.created_at:
                zone = self._fvg

                if (
                    zone.direction == Direction.BULLISH
                    and bar.low <= zone.upper
                    and bar.high >= zone.lower
                    and bar.close >= zone.lower
                ):
                    self.events.append(
                        Event(
                            timestamp=bar.timestamp,
                            bar_index=i,
                            event_type=EventType.RETEST,
                            direction=Direction.BULLISH,
                            price=bar.close,
                        )
                    )
                    self._fvg = None

                elif (
                    zone.direction == Direction.BEARISH
                    and bar.high >= zone.lower
                    and bar.low <= zone.upper
                    and bar.close <= zone.upper
                ):
                    self.events.append(
                        Event(
                            timestamp=bar.timestamp,
                            bar_index=i,
                            event_type=EventType.RETEST,
                            direction=Direction.BEARISH,
                            price=bar.close,
                        )
                    )
                    self._fvg = None

        return list(self.events)
