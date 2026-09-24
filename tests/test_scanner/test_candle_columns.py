from datetime import datetime, timedelta, timezone

from app.scanner.buffered_candle import BufferedCandle
from app.scanner.candle_columns import CandleColumns

BASE = datetime(2026, 9, 23, 14, 30, tzinfo=timezone.utc)


def _candle(minute: int, close: float = 10.0, volume: float | None = 100.0, vwap: float | None = None) -> BufferedCandle:
    return BufferedCandle(symbol="AAPL", timestamp=BASE + timedelta(minutes=minute), open=9.5, high=11.0,
                          low=9.0, close=close, volume=volume, vwap=vwap)


def test_a_stored_candle_comes_back_identical():
    columns = CandleColumns("AAPL", [_candle(0, close=10.25, vwap=10.1)])

    assert columns[0] == _candle(0, close=10.25, vwap=10.1)


def test_missing_values_come_back_as_none():
    columns = CandleColumns("AAPL", [_candle(0, volume=None)])

    restored = columns[0]

    assert restored.volume is None and restored.vwap is None and restored.impVolatility is None


def test_trim_keeps_only_the_newest_candles():
    columns = CandleColumns("AAPL", [_candle(i, close=float(i)) for i in range(5)])

    columns.trim(2)

    assert [c.close for c in columns] == [3.0, 4.0]


def test_index_of_finds_a_candle_by_timestamp_and_misses_unknown_ones():
    columns = CandleColumns("AAPL", [_candle(i) for i in range(3)])

    assert columns.index_of(BASE + timedelta(minutes=1)) == 1
    assert columns.index_of(BASE + timedelta(minutes=9)) is None


def test_replace_returns_the_previous_candle_and_stores_the_new_one():
    columns = CandleColumns("AAPL", [_candle(0, volume=100.0)])

    previous = columns.replace(0, _candle(0, volume=120.0))

    assert previous.volume == 100.0 and columns[0].volume == 120.0


def test_materialize_returns_plain_candles_in_order():
    columns = CandleColumns("AAPL", [_candle(i) for i in range(3)])

    candles = columns.materialize()

    assert [c.timestamp for c in candles] == [BASE + timedelta(minutes=i) for i in range(3)]
    assert all(isinstance(c, BufferedCandle) for c in candles)
