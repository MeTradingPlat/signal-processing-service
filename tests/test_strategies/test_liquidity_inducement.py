from datetime import datetime, timezone

from app.models.enums import EnumFiltro, EnumParametro
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorFloat, ValorInteger, ValorString
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.liquidity_inducement import (
    AccelerationDecelerationStrategy, ConfirmationCandleStrategy,
    LiquidityGrabCandleStrategy, OrderBlockImbalanceStrategy,
    RangeConfluenceStrategy, RangeExtremeProximityStrategy,
)

_TODAY = datetime.now(timezone.utc)


def _candle(open_=1.0, high=1.0, low=1.0, close=1.0) -> CandleResponse:
    return CandleResponse(symbol="AAPL", timestamp=_TODAY, open=open_, high=high, low=low, close=close)


def _velas_rango(base: float, close_ultima: float | None = None) -> list[CandleResponse]:
    """3 velas cuya estructura de swing_range (confirmacion=2) da
    (base, base+4) -- ver calculo a mano en el diseno de estos tests."""
    c0 = _candle(high=base + 2, low=base, close=base + 1)
    c1 = _candle(high=base + 3, low=base + 1, close=base + 2)
    ultima_close = close_ultima if close_ultima is not None else base + 3
    c2 = _candle(high=base + 4, low=base + 2, close=ultima_close)
    return [c0, c1, c2]


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


def test_order_block_imbalance_refines_near_upstream_zone():
    filtro = _filtro(EnumFiltro.ORDER_BLOCK_IMBALANCE,
                      **{EnumParametro.LOOKBACK_VELAS_ORDER_BLOCK_IMBALANCE: 1,
                         EnumParametro.DIRECCION_ORDER_BLOCK_IMBALANCE: "ALCISTA"})
    candles = [_candle(high=10, low=9), _candle(high=12, low=11), _candle(high=16, low=15)]
    # La zona del FVG es (10, 15) -- una zona previa cercana debe aceptarse.
    data = MarketData(symbol="AAPL", candles=candles, zona=(9.5, 15.5))
    strategy = OrderBlockImbalanceStrategy(filtro)
    assert strategy.compute_value(data) == 1.0
    assert strategy.ultima_zona == (10, 15)


def test_order_block_imbalance_rejects_far_upstream_zone():
    filtro = _filtro(EnumFiltro.ORDER_BLOCK_IMBALANCE,
                      **{EnumParametro.LOOKBACK_VELAS_ORDER_BLOCK_IMBALANCE: 1,
                         EnumParametro.DIRECCION_ORDER_BLOCK_IMBALANCE: "ALCISTA"})
    candles = [_candle(high=10, low=9), _candle(high=12, low=11), _candle(high=16, low=15)]
    # Zona previa muy lejos del FVG (10, 15) encontrado -- no cuenta como
    # refinamiento, aunque el imbalance en si mismo exista.
    data = MarketData(symbol="AAPL", candles=candles, zona=(500.0, 510.0))
    strategy = OrderBlockImbalanceStrategy(filtro)
    assert strategy.compute_value(data) == 0.0
    assert strategy.ultima_zona is None


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


def test_liquidity_grab_candle_near_zone_matches():
    filtro = _filtro(EnumFiltro.LIQUIDITY_GRAB_CANDLE,
                      **{EnumParametro.LOOKBACK_VELAS_LIQUIDITY_GRAB_CANDLE: 2,
                         EnumParametro.PROPORCION_MECHA_CUERPO_LIQUIDITY_GRAB_CANDLE: 2.0,
                         EnumParametro.DIRECCION_LIQUIDITY_GRAB_CANDLE: "ALCISTA"})
    prior = [_candle(low=95, high=105), _candle(low=96, high=106)]
    curr = _candle(open_=100, close=100.5, high=101, low=90)
    candles = prior + [curr]
    data = MarketData(symbol="AAPL", candles=candles, zona=(89.0, 92.0))
    assert LiquidityGrabCandleStrategy(filtro).compute_value(data) == 1.0


def test_liquidity_grab_candle_far_from_zone_does_not_match():
    filtro = _filtro(EnumFiltro.LIQUIDITY_GRAB_CANDLE,
                      **{EnumParametro.LOOKBACK_VELAS_LIQUIDITY_GRAB_CANDLE: 2,
                         EnumParametro.PROPORCION_MECHA_CUERPO_LIQUIDITY_GRAB_CANDLE: 2.0,
                         EnumParametro.DIRECCION_LIQUIDITY_GRAB_CANDLE: "ALCISTA"})
    prior = [_candle(low=95, high=105), _candle(low=96, high=106)]
    curr = _candle(open_=100, close=100.5, high=101, low=90)
    candles = prior + [curr]
    data = MarketData(symbol="AAPL", candles=candles, zona=(500.0, 510.0))
    assert LiquidityGrabCandleStrategy(filtro).compute_value(data) == 0.0


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


def test_acceleration_deceleration_near_zone_matches():
    filtro = _filtro(EnumFiltro.ACCELERATION_DECELERATION,
                      **{EnumParametro.VELAS_ACELERACION_ACCELERATION_DECELERATION: 2,
                         EnumParametro.VELAS_DESACELERACION_ACCELERATION_DECELERATION: 1,
                         EnumParametro.PROPORCION_DESACELERACION_ACCELERATION_DECELERATION: 0.4})
    candles = [
        _candle(open_=100, close=105, high=105, low=100),
        _candle(open_=105, close=112, high=112, low=105),
        _candle(open_=112, close=112.5, high=112.5, low=112),
    ]
    data = MarketData(symbol="AAPL", candles=candles, zona=(111.0, 114.0))
    assert AccelerationDecelerationStrategy(filtro).compute_value(data) == 1.0


def test_acceleration_deceleration_far_from_zone_does_not_match():
    filtro = _filtro(EnumFiltro.ACCELERATION_DECELERATION,
                      **{EnumParametro.VELAS_ACELERACION_ACCELERATION_DECELERATION: 2,
                         EnumParametro.VELAS_DESACELERACION_ACCELERATION_DECELERATION: 1,
                         EnumParametro.PROPORCION_DESACELERACION_ACCELERATION_DECELERATION: 0.4})
    candles = [
        _candle(open_=100, close=105, high=105, low=100),
        _candle(open_=105, close=112, high=112, low=105),
        _candle(open_=112, close=112.5, high=112.5, low=112),
    ]
    data = MarketData(symbol="AAPL", candles=candles, zona=(500.0, 510.0))
    assert AccelerationDecelerationStrategy(filtro).compute_value(data) == 0.0


def test_confirmation_candle_bullish_power_candle_matches():
    filtro = _filtro(EnumFiltro.CONFIRMATION_CANDLE,
                      **{EnumParametro.PROPORCION_CUERPO_MINIMA_CONFIRMATION_CANDLE: 0.7,
                         EnumParametro.DIRECCION_CONFIRMATION_CANDLE: "ALCISTA"})
    prev = _candle(high=100, low=95)
    mid = _candle(high=100.5, low=96)
    curr = _candle(open_=101, close=105, high=105, low=101)
    candles = [prev, mid, curr]
    assert ConfirmationCandleStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 1.0


def test_confirmation_candle_without_imbalance_does_not_match():
    filtro = _filtro(EnumFiltro.CONFIRMATION_CANDLE,
                      **{EnumParametro.PROPORCION_CUERPO_MINIMA_CONFIRMATION_CANDLE: 0.7,
                         EnumParametro.DIRECCION_CONFIRMATION_CANDLE: "ALCISTA"})
    prev = _candle(high=100, low=95)
    mid = _candle(high=100.5, low=96)
    curr = _candle(open_=99, close=103, high=103, low=99)
    candles = [prev, mid, curr]
    assert ConfirmationCandleStrategy(filtro).compute_value(MarketData(symbol="AAPL", candles=candles)) == 0.0


def test_confirmation_candle_with_near_zone_matches():
    filtro = _filtro(EnumFiltro.CONFIRMATION_CANDLE,
                      **{EnumParametro.PROPORCION_CUERPO_MINIMA_CONFIRMATION_CANDLE: 0.7,
                         EnumParametro.DIRECCION_CONFIRMATION_CANDLE: "ALCISTA"})
    prev = _candle(high=100, low=95)
    mid = _candle(high=100.5, low=96)
    curr = _candle(open_=101, close=105, high=105, low=101)
    candles = [prev, mid, curr]
    data = MarketData(symbol="AAPL", candles=candles, zona=(100.0, 106.0))
    assert ConfirmationCandleStrategy(filtro).compute_value(data) == 1.0


def test_confirmation_candle_far_from_zone_does_not_match():
    filtro = _filtro(EnumFiltro.CONFIRMATION_CANDLE,
                      **{EnumParametro.PROPORCION_CUERPO_MINIMA_CONFIRMATION_CANDLE: 0.7,
                         EnumParametro.DIRECCION_CONFIRMATION_CANDLE: "ALCISTA"})
    prev = _candle(high=100, low=95)
    mid = _candle(high=100.5, low=96)
    curr = _candle(open_=101, close=105, high=105, low=101)
    candles = [prev, mid, curr]
    # Zona muy lejos del cierre de la vela de confirmacion (105).
    data = MarketData(symbol="AAPL", candles=candles, zona=(500.0, 510.0))
    assert ConfirmationCandleStrategy(filtro).compute_value(data) == 0.0


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


def _filtro_confluencia(**overrides) -> Filtro:
    params = {
        EnumParametro.LOOKBACK_VELAS_RANGE_CONFLUENCE_D1_H4_H1: 3,
        EnumParametro.CONFIRMACION_VELAS_RANGE_CONFLUENCE_D1_H4_H1: 2,
        EnumParametro.PROPORCION_PROXIMIDAD_RANGE_CONFLUENCE_D1_H4_H1: 0.5,
        EnumParametro.DIRECCION_RANGE_CONFLUENCE_D1_H4_H1: "ALCISTA",
    }
    params.update(overrides)
    return _filtro(EnumFiltro.RANGE_CONFLUENCE_D1_H4_H1, **params)


def test_range_confluence_overlapping_ranges_matches_and_exposes_zone():
    filtro = _filtro_confluencia()
    d1 = _velas_rango(100, close_ultima=101.5)
    h4 = _velas_rango(101)
    h1 = _velas_rango(99)
    data = MarketData(symbol="AAPL", candles=d1, velas_extra={"H4": h4, "H1": h1})
    strategy = RangeConfluenceStrategy(filtro)
    assert strategy.compute_value(data) == 1.0
    # Interseccion de (100,104), (101,105) y (99,103) -> (101,103).
    assert strategy.ultima_zona == (101, 103)


def test_range_confluence_no_overlap_does_not_match():
    filtro = _filtro_confluencia()
    d1 = _velas_rango(100)
    h4 = _velas_rango(300)
    h1 = _velas_rango(500)
    data = MarketData(symbol="AAPL", candles=d1, velas_extra={"H4": h4, "H1": h1})
    strategy = RangeConfluenceStrategy(filtro)
    assert strategy.compute_value(data) == 0.0
    assert strategy.ultima_zona is None


def test_range_confluence_missing_extra_timeframe_returns_none():
    filtro = _filtro_confluencia()
    d1 = _velas_rango(100)
    data = MarketData(symbol="AAPL", candles=d1, velas_extra=None)
    assert RangeConfluenceStrategy(filtro).compute_value(data) is None
