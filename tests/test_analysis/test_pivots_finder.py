from datetime import datetime, timedelta

from app.analysis.pivots_finder import find_pivots
from app.scanner.marketdata_models import CandleResponse


def _candle(day: int, high: float, low: float) -> CandleResponse:
    close = (high + low) / 2
    return CandleResponse(
        symbol="TEST", timestamp=datetime(2026, 1, 1) + timedelta(days=day),
        open=close, high=high, low=low, close=close,
    )


def test_finds_strong_resistance_and_support_around_price():
    candles = [_candle(i, 100.2, 99.8) for i in range(30)]
    candles[5] = _candle(5, 101.0, 99.8)   # pico por encima del precio actual
    candles[8] = _candle(8, 100.2, 99.0)   # valle por debajo del precio actual

    resistencias, soportes = find_pivots(candles, current_price=100.0, atr_length=14, number_pivots=1)

    assert resistencias == [(candles[5].timestamp, 101.0)]
    assert soportes == [(candles[8].timestamp, 99.0)]


def test_falls_back_to_weak_pivot_when_no_strong_found():
    # Todo el fondo queda por ENCIMA del precio actual -- ningun pico/valle
    # fuerte posible (fuerte exige pico arriba o valle abajo del precio).
    candles = [_candle(i, 100.7, 100.5) for i in range(30)]
    candles[10] = _candle(10, 100.7, 100.2)  # valle que sigue por encima del precio

    resistencias, _ = find_pivots(candles, current_price=100.0, atr_length=14, number_pivots=1)

    assert resistencias == [(candles[10].timestamp, 100.2)]


def test_returns_empty_when_nothing_found():
    candles = [_candle(i, 100.1, 99.9) for i in range(30)]

    resistencias, soportes = find_pivots(candles, current_price=100.0, atr_length=14, number_pivots=1)

    assert resistencias == []
    assert soportes == []
