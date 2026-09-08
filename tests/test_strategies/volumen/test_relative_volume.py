from datetime import datetime, timezone

from app.models.enums import EnumCondicional, EnumFiltro, EnumParametro, EnumTipoValor
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.volumen.relative_volume import RelativeVolumeStrategy

_NOW = datetime.now(timezone.utc)


def _candle(volume: float) -> CandleResponse:
    return CandleResponse(symbol="AAPL", timestamp=_NOW, volume=volume)


def _strategy(condicion: EnumCondicional, valor1: float) -> RelativeVolumeStrategy:
    filtro = Filtro(
        enumFiltro=EnumFiltro.RELATIVE_VOLUME,
        parametros=[
            Parametro(
                enumParametro=EnumParametro.CONDICION, etiqueta="",
                objValorSeleccionado=ValorCondicional(
                    enumCondicional=condicion,
                    enumTipoValor=EnumTipoValor.CONDICIONAL,
                    valor1=valor1,
                ),
            )
        ],
    )
    return RelativeVolumeStrategy(filtro)


def test_relative_volume_above_threshold():
    strategy = _strategy(EnumCondicional.MAYOR_QUE, 150.0)
    data = MarketData(symbol="AAPL", candles=[_candle(1000), _candle(1000), _candle(3000)])
    assert strategy.evaluate(data)


def test_relative_volume_counts_zero_volume_candles_instead_of_dropping_them():
    # Regression: antes `if c.volume` descartaba las velas de volumen 0 del
    # promedio de las previas en vez de contarlas -- eso INFLA el promedio
    # (mismo bug de AverageVolumeStrategy, confirmado en vivo con CTAS), lo
    # que aca hace que un spike real en un simbolo con huecos de trading
    # (14 velas en 0 + 1 real) parezca mucho MAS chico de lo que es.
    # Descartando ceros: avg=100 (solo la vela real) -> 300/100=300%.
    # Contando ceros: avg=100/15=6.67 -> 300/6.67=~4500%, la cifra real.
    strategy = _strategy(EnumCondicional.MAYOR_QUE, 1000.0)
    data = MarketData(symbol="CTAS", candles=[_candle(0)] * 14 + [_candle(100)] + [_candle(300)])
    assert strategy.evaluate(data)
