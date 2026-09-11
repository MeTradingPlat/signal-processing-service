from datetime import datetime, timezone

from app.analysis.indicators import near_zone, swing_range, zonas_cercanas
from app.scanner.marketdata_models import CandleResponse

_TODAY = datetime.now(timezone.utc)


def _candle(high, low) -> CandleResponse:
    return CandleResponse(symbol="AAPL", timestamp=_TODAY, open=low, high=high, low=low, close=high)


def test_swing_range_moves_after_confirmed_breakout():
    # Rompe a un nuevo maximo (15) y retrocede 2 velas seguidas sin
    # superarlo -- el minimo del rango debe "moverse" al minimo alcanzado
    # desde el rompimiento (11), no quedarse en el minimo original (10).
    candles = [_candle(12, 10), _candle(15, 13), _candle(14, 12), _candle(13, 11)]
    assert swing_range(candles, confirmacion_velas=2) == (11, 15)


def test_swing_range_bearish_breakout_moves_high():
    candles = [_candle(12, 10), _candle(9, 7), _candle(10, 8), _candle(11, 9)]
    assert swing_range(candles, confirmacion_velas=2) == (7, 11)


def test_swing_range_not_enough_candles_returns_none():
    candles = [_candle(12, 10), _candle(13, 11)]
    assert swing_range(candles, confirmacion_velas=2) is None


def test_near_zone_price_inside_zone():
    candles = [_candle(101, 99) for _ in range(5)]
    assert near_zone(100.5, (100.0, 101.0), candles) is True


def test_near_zone_price_far_outside_zone():
    candles = [_candle(101, 99) for _ in range(5)]
    assert near_zone(200.0, (100.0, 101.0), candles) is False


def test_near_zone_uses_volatility_floor_for_tiny_zone():
    # Zona degenerada (altura 0) en un simbolo con velas de rango 5 --
    # sin el piso de volatilidad, cualquier precio distinto del extremo
    # exacto fallaria. precio a 3 de la zona debe pasar por el piso de
    # volatilidad (k=1.0 * rango promedio 5).
    candles = [_candle(105, 100) for _ in range(5)]
    assert near_zone(103.0, (100.0, 100.0), candles) is True


def test_zonas_cercanas_overlapping():
    candles = [_candle(101, 99) for _ in range(5)]
    assert zonas_cercanas((99.5, 100.5), (100.0, 101.0), candles) is True


def test_zonas_cercanas_far_apart():
    candles = [_candle(101, 99) for _ in range(5)]
    assert zonas_cercanas((10.0, 11.0), (100.0, 101.0), candles) is False
