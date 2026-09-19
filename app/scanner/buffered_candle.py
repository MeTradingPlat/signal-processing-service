from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(slots=True)
class BufferedCandle:
    symbol: str
    timestamp: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    vwap: Optional[float] = None
    impVolatility: Optional[float] = None


def candle_from_bar(symbol: str, bar: dict) -> BufferedCandle:
    return BufferedCandle(
        symbol=symbol,
        timestamp=datetime.fromtimestamp(bar["time"], tz=timezone.utc),
        open=bar.get("open"), high=bar.get("high"), low=bar.get("low"),
        close=bar.get("close"), volume=bar.get("volume"),
    )
