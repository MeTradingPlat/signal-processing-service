from datetime import datetime, timezone

from app.models.enums import EnumFiltro, EnumParametro
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorFloat, ValorInteger, ValorString
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.liquidity_inducement import (
    AccelerationDecelerationStrategy, ConfirmationCandleStrategy,
    LiquidityGrabCandleStrategy, OrderBlockImbalanceStrategy,
    RangeExtremeProximityStrategy,
)

_TODAY = datetime.now(timezone.utc)


def _candle(open_=1.0, high=1.0, low=1.0, close=1.0) -> CandleResponse:
    return CandleResponse(symbol="AAPL", timestamp=_TODAY, open=open_, high=high, low=low, close=close)


def _filtro(enum_filtro: EnumFiltro, **params) -> Filtro:
    parametros = []
    for key, val in params.items():
        if isinstance(val, bool):
            v = ValorString(valor=str(val))
        elif isinstance(val, int):
            v = ValorInteger(valor=val)
        elif isinstance(val, float):
            v = ValorFloat(valor=val)
        else:
            v = ValorString(valor=val)
        parametros.append(Parametro(enumParametro=key, etiqueta="", objValorSeleccionado=v))
    return Filtro(enumFiltro=enum_filtro, parametros=parametros)


def test_order_block_imbalance_detects_bullish_fvg():
    filtro = _filtro(EnumFiltro.ORDER_BLOCK_IMBALANCE,
                      **{EnumParametro.LOOKBACK_VELAS_ORDER_BLOCK_IMBALANCE: 1,
                         EnumParametro.DIRECCION_ORDER_BLOCK_IMBALANCE: "ALCISTA"})
    candles = [_candle(high=10, low=9), _candle(high=12, low=11), _candle(high=16, low=15)]
    assert OrderBlockImbalanceStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 1.0


def test_order_block_imbalance_no_gap_does_not_match():
    filtro = _filtro(EnumFiltro.ORDER_BLOCK_IMBALANCE,
                      **{EnumParametro.LOOKBACK_VELAS_ORDER_BLOCK_IMBALANCE: 1,
                         EnumParametro.DIRECCION_ORDER_BLOCK_IMBALANCE: "ALCISTA"})
    candles = [_candle(high=10, low=9), _candle(high=12, low=11), _candle(high=9.5, low=8)]
    assert OrderBlockImbalanceStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 0.0


def test_liquidity_grab_candle_bullish_sweep_matches():
    filtro = _filtro(EnumFiltro.LIQUIDITY_GRAB_CANDLE,
                      **{EnumParametro.LOOKBACK_VELAS_LIQUIDITY_GRAB_CANDLE: 2,
                         EnumParametro.PROPORCION_MECHA_CUERPO_LIQUIDITY_GRAB_CANDLE: 2.0,
                         EnumParametro.DIRECCION_LIQUIDITY_GRAB_CANDLE: "ALCISTA"})
    prior = [_candle(low=95, high=105), _candle(low=96, high=106)]
    # mecha inferior = min(open,close) - low = 100 - 90 = 10 >= 2 * cuerpo(0.5)
    curr = _candle(open_=100, close=100.5, high=101, low=90)
    candles = prior + [curr]
    assert LiquidityGrabCandleStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 1.0


def test_liquidity_grab_candle_no_close_back_inside_does_not_match():
    filtro = _filtro(EnumFiltro.LIQUIDITY_GRAB_CANDLE,
                      **{EnumParametro.LOOKBACK_VELAS_LIQUIDITY_GRAB_CANDLE: 2,
                         EnumParametro.PROPORCION_MECHA_CUERPO_LIQUIDITY_GRAB_CANDLE: 2.0,
                         EnumParametro.DIRECCION_LIQUIDITY_GRAB_CANDLE: "ALCISTA"})
    prior = [_candle(low=95, high=105), _candle(low=96, high=106)]
    # cierra por debajo del minimo previo (95) -- no hay barrida confirmada, sigue rompiendo
    curr = _candle(open_=94, close=94, high=94.5, low=90)
    candles = prior + [curr]
    assert LiquidityGrabCandleStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 0.0


def test_acceleration_deceleration_matches_when_body_shrinks():
    filtro = _filtro(EnumFiltro.ACCELERATION_DECELERATION,
                      **{EnumParametro.VELAS_ACELERACION_ACCELERATION_DECELERATION: 2,
                         EnumParametro.VELAS_DESACELERACION_ACCELERATION_DECELERATION: 1,
                         EnumParametro.PROPORCION_DESACELERACION_ACCELERATION_DECELERATION: 0.4})
    candles = [
        _candle(open_=100, close=105, high=105, low=100),
        _candle(open_=105, close=112, high=112, low=105),
        _candle(open_=112, close=112.5, high=112.5, low=112),
    ]
    assert AccelerationDecelerationStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 1.0


def test_acceleration_deceleration_no_shrink_does_not_match():
    filtro = _filtro(EnumFiltro.ACCELERATION_DECELERATION,
                      **{EnumParametro.VELAS_ACELERACION_ACCELERATION_DECELERATION: 2,
                         EnumParametro.VELAS_DESACELERACION_ACCELERATION_DECELERATION: 1,
                         EnumParametro.PROPORCION_DESACELERACION_ACCELERATION_DECELERATION: 0.4})
    candles = [
        _candle(open_=100, close=105, high=105, low=100),
        _candle(open_=105, close=112, high=112, low=105),
        _candle(open_=112, close=117, high=117, low=112),
    ]
    assert AccelerationDecelerationStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 0.0


def test_confirmation_candle_bullish_power_candle_matches():
    filtro = _filtro(EnumFiltro.CONFIRMATION_CANDLE,
                      **{EnumParametro.PROPORCION_CUERPO_MINIMA_CONFIRMATION_CANDLE: 0.7,
                         EnumParametro.DIRECCION_CONFIRMATION_CANDLE: "ALCISTA"})
    prev = _candle(high=100, low=95)
    curr = _candle(open_=101, close=105, high=105, low=101)
    assert ConfirmationCandleStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=[prev, curr])) == 1.0


def test_confirmation_candle_without_imbalance_does_not_match():
    filtro = _filtro(EnumFiltro.CONFIRMATION_CANDLE,
                      **{EnumParametro.PROPORCION_CUERPO_MINIMA_CONFIRMATION_CANDLE: 0.7,
                         EnumParametro.DIRECCION_CONFIRMATION_CANDLE: "ALCISTA"})
    prev = _candle(high=100, low=95)
    curr = _candle(open_=99, close=103, high=103, low=99)
    assert ConfirmationCandleStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=[prev, curr])) == 0.0


def test_range_extreme_proximity_bullish_near_low_matches():
    filtro = _filtro(EnumFiltro.RANGE_EXTREME_PROXIMITY,
                      **{EnumParametro.LOOKBACK_VELAS_RANGE_EXTREME_PROXIMITY: 3,
                         EnumParametro.PROPORCION_PROXIMIDAD_RANGE_EXTREME_PROXIMITY: 0.15,
                         EnumParametro.DIRECCION_RANGE_EXTREME_PROXIMITY: "ALCISTA"})
    candles = [
        _candle(high=110, low=105),
        _candle(high=108, low=100),
        _candle(open_=101, close=100.5, high=101, low=100),
    ]
    assert RangeExtremeProximityStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 1.0


def test_range_extreme_proximity_bearish_near_high_matches():
    filtro = _filtro(EnumFiltro.RANGE_EXTREME_PROXIMITY,
                      **{EnumParametro.LOOKBACK_VELAS_RANGE_EXTREME_PROXIMITY: 3,
                         EnumParametro.PROPORCION_PROXIMIDAD_RANGE_EXTREME_PROXIMITY: 0.15,
                         EnumParametro.DIRECCION_RANGE_EXTREME_PROXIMITY: "BAJISTA"})
    candles = [
        _candle(high=100, low=90),
        _candle(high=105, low=92),
        _candle(open_=109, close=109.5, high=110, low=109),
    ]
    assert RangeExtremeProximityStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 1.0


def test_range_extreme_proximity_middle_of_range_does_not_match():
    filtro = _filtro(EnumFiltro.RANGE_EXTREME_PROXIMITY,
                      **{EnumParametro.LOOKBACK_VELAS_RANGE_EXTREME_PROXIMITY: 3,
                         EnumParametro.PROPORCION_PROXIMIDAD_RANGE_EXTREME_PROXIMITY: 0.15,
                         EnumParametro.DIRECCION_RANGE_EXTREME_PROXIMITY: "ALCISTA"})
    candles = [
        _candle(high=110, low=105),
        _candle(high=108, low=100),
        _candle(open_=105, close=105, high=106, low=104),
    ]
    assert RangeExtremeProximityStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 0.0
