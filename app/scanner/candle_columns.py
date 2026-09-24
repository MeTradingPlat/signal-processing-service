import math
from array import array
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional

from app.scanner.buffered_candle import BufferedCandle

_FIELDS = ("open", "high", "low", "close", "volume", "vwap", "impVolatility")
_MISSING = math.nan


def _to_column(value: Optional[float]) -> float:
    return _MISSING if value is None else value


def _from_column(value: float) -> Optional[float]:
    return None if value != value else value


class CandleColumns:
    __slots__ = ("symbol", "_timestamps", "_columns")

    def __init__(self, symbol: str, candles: Iterable[BufferedCandle] = ()):
        self.symbol = symbol
        self._timestamps = array("d")
        self._columns = {name: array("d") for name in _FIELDS}
        for candle in candles:
            self.append(candle)

    def __len__(self) -> int:
        return len(self._timestamps)

    def __getitem__(self, index: int) -> BufferedCandle:
        return BufferedCandle(
            symbol=self.symbol,
            timestamp=datetime.fromtimestamp(self._timestamps[index], tz=timezone.utc),
            **{name: _from_column(column[index]) for name, column in self._columns.items()},
        )

    def __iter__(self) -> Iterator[BufferedCandle]:
        return (self[i] for i in range(len(self)))

    def append(self, candle: BufferedCandle) -> None:
        self._timestamps.append(candle.timestamp.timestamp())
        for name, column in self._columns.items():
            column.append(_to_column(getattr(candle, name)))

    def replace(self, index: int, candle: BufferedCandle) -> BufferedCandle:
        previous = self[index]
        self._timestamps[index] = candle.timestamp.timestamp()
        for name, column in self._columns.items():
            column[index] = _to_column(getattr(candle, name))
        return previous

    def trim(self, keep: int) -> None:
        del self._timestamps[:-keep]
        for column in self._columns.values():
            del column[:-keep]

    def index_of(self, timestamp: datetime) -> Optional[int]:
        target = timestamp.timestamp()
        for i in range(len(self._timestamps) - 1, -1, -1):
            if self._timestamps[i] == target:
                return i
        return None

    def materialize(self) -> list[BufferedCandle]:
        return list(self)
