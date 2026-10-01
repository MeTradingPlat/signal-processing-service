from datetime import datetime, timedelta, timezone

from app.models.enums import EnumFiltro, EnumParametro
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorInteger
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.volatilidad import RelativeRangeStrategy

_NOW = datetime.now(timezone.utc)


def _candle(high: float, low: float, minutes_ago: int) -> CandleResponse:
    return CandleResponse(
        symbol="AAPL", timestamp=_NOW - timedelta(minutes=minutes_ago),
        high=high, low=low, close=(high + low) / 2,
    )


def _candles_with_growing_range(n: int) -> list[CandleResponse]:
    return [_candle(high=100 + (1 + i), low=100 - (1 + i), minutes_ago=n - i) for i in range(n)]


def _strategy(periodo: int | None = None) -> RelativeRangeStrategy:
    parametros = []
    if periodo is not None:
        parametros.append(Parametro(
            enumParametro=EnumParametro.PERIODO_ATR_RELATIVE_RANGE, etiqueta="",
            objValorSeleccionado=ValorInteger(valor=periodo),
        ))
    return RelativeRangeStrategy(Filtro(enumFiltro=EnumFiltro.RELATIVE_RANGE, parametros=parametros))


def test_default_period_matches_explicit_fourteen():
    candles = _candles_with_growing_range(20)
    data = MarketData(symbol="AAPL", candles=candles)
    assert _strategy().compute_value(data) == _strategy(periodo=14).compute_value(data)


def test_periodo_parameter_is_read_and_changes_the_result():
    # Rango de las velas crece con el tiempo -- un periodo corto de ATR pesa
    # mas las velas recientes (rango mas ancho) que uno largo, asi que deben
    # dar un ATR (y por lo tanto un RelativeRange) distinto.
    candles = _candles_with_growing_range(20)
    data = MarketData(symbol="AAPL", candles=candles)
    value_short = _strategy(periodo=2).compute_value(data)
    value_long = _strategy(periodo=20).compute_value(data)
    assert value_short != value_long
