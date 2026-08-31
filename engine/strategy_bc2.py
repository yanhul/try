from dataclasses import dataclass
from typing import Optional

from .events import Direction, Event, EventType, MarketBar


SWEEP_LOOKBACK = 3


@dataclass(frozen=True)
class FVGZone:
    direction: Direction
    created_at: int
    lower: float
    upper: float


class BC2SwingSweepStrategy:
    """Single-hypothesis BC2 candidate.

    Only the liquidity-sweep definition changes versus ReferenceStrategy:
    price must sweep the extreme of the previous 3 completed bars and close
    back through that level. MSS/FVG/retest logic is otherwise unchanged.
    """

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

            if i >= SWEEP_LOOKBACK:
                prior = bars[i - SWEEP_LOOKBACK:i]
                prior_low = min(x.low for x in prior)
                prior_high = max(x.high for x in prior)

                if bar.low < prior_low and bar.close > prior_low:
                    event = Event(
                        timestamp=bar.timestamp,
                        bar_index=i,
                        event_type=EventType.LIQUIDITY_SWEEP,
                        direction=Direction.BULLISH,
                        price=prior_low,
                    )
                    self.events.append(event)
                    self._sweep = event

                elif bar.high > prior_high and bar.close < prior_high:
                    event = Event(
                        timestamp=bar.timestamp,
                        bar_index=i,
                        event_type=EventType.LIQUIDITY_SWEEP,
                        direction=Direction.BEARISH,
                        price=prior_high,
                    )
                    self.events.append(event)
                    self._sweep = event

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

            if i >= 2 and self._sweep is not None:
                left = bars[i - 2]

                if (
                    self._sweep.event_type == EventType.MSS
                    and self._sweep.direction == Direction.BULLISH
                    and bar.low > left.high
                ):
                    zone = FVGZone(Direction.BULLISH, i, left.high, bar.low)
                    self._fvg = zone
                    self.events.append(Event(bar.timestamp, i, EventType.FVG, Direction.BULLISH, zone.lower))

                elif (
                    self._sweep.event_type == EventType.MSS
                    and self._sweep.direction == Direction.BEARISH
                    and bar.high < left.low
                ):
                    zone = FVGZone(Direction.BEARISH, i, bar.high, left.low)
                    self._fvg = zone
                    self.events.append(Event(bar.timestamp, i, EventType.FVG, Direction.BEARISH, zone.upper))

            if self._fvg is not None and i > self._fvg.created_at:
                zone = self._fvg

                if (
                    zone.direction == Direction.BULLISH
                    and bar.low <= zone.upper
                    and bar.high >= zone.lower
                    and bar.close >= zone.lower
                ):
                    self.events.append(Event(bar.timestamp, i, EventType.RETEST, Direction.BULLISH, bar.close))
                    self._fvg = None

                elif (
                    zone.direction == Direction.BEARISH
                    and bar.high >= zone.lower
                    and bar.low <= zone.upper
                    and bar.close <= zone.upper
                ):
                    self.events.append(Event(bar.timestamp, i, EventType.RETEST, Direction.BEARISH, bar.close))
                    self._fvg = None

        return list(self.events)
