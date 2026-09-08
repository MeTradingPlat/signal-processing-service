from datetime import datetime, timezone
from app.models.enums import EnumCondicional, EnumFiltro, EnumParametro, EnumTipoValor
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.volumen.average_volume import AverageVolumeStrategy

_NOW = datetime.now(timezone.utc)


def _candle(volume: float) -> CandleResponse:
    return CandleResponse(symbol="AAPL", timestamp=_NOW, volume=volume)


def test_average_volume_below_threshold():
    filtro = Filtro(
        enumFiltro=EnumFiltro.AVERAGE_VOLUME,
        parametros=[
            Parametro(
                enumParametro=EnumParametro.CONDICION, etiqueta="",
                objValorSeleccionado=ValorCondicional(
                    enumCondicional=EnumCondicional.MENOR_QUE,
                    enumTipoValor=EnumTipoValor.CONDICIONAL,
                    valor1=50000.0,
                ),
            )
        ],
    )
    strategy = AverageVolumeStrategy(filtro)
    data = MarketData(symbol="AAPL", candles=[_candle(10000), _candle(20000), _candle(30000)])
    assert strategy.evaluate(data)


def test_average_volume_counts_zero_volume_candles_instead_of_dropping_them():
    # Regression: antes `if c.volume` descartaba las velas de volumen 0 del
    # promedio en vez de contarlas -- confirmado en vivo con CTAS, una sola
    # vela real de 100 acciones en un rango de 15 velas (el resto en 0) daba
    # promedio=100 (paso el filtro > 50) en vez del promedio real (100/15
    # ~= 6.67, no deberia pasar un umbral razonable para ese simbolo).
    filtro = Filtro(
        enumFiltro=EnumFiltro.AVERAGE_VOLUME,
        parametros=[
            Parametro(
                enumParametro=EnumParametro.CONDICION, etiqueta="",
                objValorSeleccionado=ValorCondicional(
                    enumCondicional=EnumCondicional.MAYOR_QUE,
                    enumTipoValor=EnumTipoValor.CONDICIONAL,
                    valor1=50.0,
                ),
            )
        ],
    )
    strategy = AverageVolumeStrategy(filtro)
    data = MarketData(symbol="CTAS", candles=[_candle(100)] + [_candle(0)] * 14)
    assert not strategy.evaluate(data)
