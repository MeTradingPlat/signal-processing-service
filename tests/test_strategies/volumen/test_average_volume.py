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
