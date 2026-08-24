"""Regression (2026-08-24): warrants con 1-2 velas al dia senialaban con
datos degenerados -- el escaner 'PRUEBA 23344' emitio KRAQW/CINGW/SCAGW
porque el fetch de precios estaba caido (el filtro de volumen quedo sin
aplicar) y las estrategias de patrones pasaban con series de 1-2 velas."""
from datetime import datetime, timezone

from app.models.enums import EnumParametro
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.patrones import (
    BreakOverRecentHighsLowsStrategy,
    HighLowOfDayStrategy,
    NewCandleHighLowStrategy,
)


def _candle(ts: str, open: float, high: float, low: float, close: float, volume: int) -> CandleResponse:
    return CandleResponse(
        symbol="KRAQW", timeframe="M5", timestamp=ts,
        open=open, high=high, low=low, close=close, volume=volume,
    )


def _strategy(cls, **params):
    from app.models.enums import EnumFiltro
    from app.models.filtro import Filtro
    from app.models.parametro import Parametro
    from app.models.valor import ValorString
    f = Filtro(enumFiltro=EnumFiltro.UNKNOWN)
    f.parametros = [
        Parametro(enumParametro=k, objValorSeleccionado=ValorString(valor=v))
        for k, v in params.items()
    ]
    return cls(f)


def test_break_over_no_dispara_con_dos_velas():
    # KRAQW 2026-08-24: close 0.3501 > high 0.35 de la unica vela previa --
    # "romper el maximo reciente" contra un solo candle es ruido.
    candles = [
        _candle("2026-08-24T13:30:00Z", 0.35, 0.35, 0.35, 0.35, 250),
        _candle("2026-08-24T14:25:00Z", 0.376, 0.376, 0.35, 0.3501, 10650),
    ]
    s = _strategy(BreakOverRecentHighsLowsStrategy,
                  **{EnumParametro.OPCION_EXTREMO_BREAK_OVER: "HIGH"})
    assert s.compute_value(MarketData(symbol="KRAQW", candles=candles)) is None


def test_break_over_dispara_con_serie_real():
    # Con >= 3 velas y un cierre que SI supera el maximo de las previas,
    # el patron sigue funcionando.
    candles = [
        _candle("2026-08-24T13:30:00Z", 0.35, 0.35, 0.35, 0.35, 250),
        _candle("2026-08-24T13:35:00Z", 0.35, 0.36, 0.35, 0.36, 500),
        _candle("2026-08-24T13:40:00Z", 0.36, 0.38, 0.36, 0.375, 900),
    ]
    s = _strategy(BreakOverRecentHighsLowsStrategy,
                  **{EnumParametro.OPCION_EXTREMO_BREAK_OVER: "HIGH"})
    assert s.compute_value(MarketData(symbol="KRAQW", candles=candles)) == 1.0


def test_high_low_of_day_un_solo_candle_del_dia_no_pasa():
    # Un solo candle del dia: sin rango, "distancia al minimo" es indefinida.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    candles = [_candle(f"{today}T13:30:00Z", 0.35, 0.35, 0.35, 0.35, 250)]
    s = _strategy(HighLowOfDayStrategy,
                  **{EnumParametro.OPCION_EXTREMO_HIGH_LOW_DAY: "LOW"})
    assert s.compute_value(MarketData(symbol="KRAQW", candles=candles)) is None


def test_high_low_of_day_con_rango_real_sigue_funcionando():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    candles = [
        _candle(f"{today}T13:30:00Z", 0.35, 0.35, 0.35, 0.35, 250),
        _candle(f"{today}T14:25:00Z", 0.376, 0.376, 0.35, 0.3501, 10650),
    ]
    s = _strategy(HighLowOfDayStrategy,
                  **{EnumParametro.OPCION_EXTREMO_HIGH_LOW_DAY: "LOW"})
    val = s.compute_value(MarketData(symbol="KRAQW", candles=candles))
    assert val is not None and 0 <= val < 10


def test_new_candle_high_low_no_dispara_con_dos_velas():
    candles = [
        _candle("2026-08-24T13:30:00Z", 0.35, 0.35, 0.35, 0.35, 250),
        _candle("2026-08-24T14:25:00Z", 0.35, 0.36, 0.35, 0.3501, 10650),
    ]
    s = _strategy(NewCandleHighLowStrategy,
                  **{EnumParametro.OPCION_EXTREMO_NEW_CANDLE: "HIGH"})
    assert s.compute_value(MarketData(symbol="KRAQW", candles=candles)) is None
