"""Modelo de dominio: Candle (vela OHLCV)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Candle:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def get_datetime(self) -> Optional[datetime]:
        """Convierte el timestamp ISO a datetime."""
        try:
            return datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
