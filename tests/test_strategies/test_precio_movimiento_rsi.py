from datetime import datetime, timezone
import pytest
from app.scanner.marketdata_models import CandleResponse
from app.strategies.precio_movimiento import _calc_rsi

_NOW = datetime.now(timezone.utc)


def _candle(close: float) -> CandleResponse:
    return CandleResponse(symbol="AAPL", timestamp=_NOW, close=close)


def test_rsi_wilder_seed_uses_first_period_candles_not_whole_window():
    # Wilder's RSI de referencia para este caso: la seed debe salir de las
    # primeras 3 velas (-1,-1,-1), no de las primeras 3 ganancias/perdidas
    # filtradas de toda la ventana (bug anterior mezclaba momentos distintos
    # entre la seed de ganancias y la de perdidas).
    closes = [100, 99, 98, 97, 96, 101, 106]
    candles = [_candle(c) for c in closes]
    assert _calc_rsi(candles, 3) == pytest.approx(86.2068965517)


def test_rsi_no_price_movement_is_neutral():
    candles = [_candle(100) for _ in range(10)]
    assert _calc_rsi(candles, 3) == 50.0


def test_rsi_insufficient_bars_returns_none():
    candles = [_candle(100), _candle(101)]
    assert _calc_rsi(candles, 14) is None
