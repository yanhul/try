from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EventType(str, Enum):
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    MSS = "MSS"
    FVG = "FVG"
    RETEST = "RETEST"


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass(frozen=True)
class MarketBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Event:
    timestamp: datetime
    bar_index: int
    event_type: EventType
    direction: Direction
    price: float
