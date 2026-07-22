from datetime import datetime, timezone
from app.models.enums import EnumCondicional, EnumFiltro, EnumParametro, EnumTipoValor
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.volumen.volume_spike import VolumeSpikeStrategy

_NOW = datetime.now(timezone.utc)


def _candle(volume: float) -> CandleResponse:
    return CandleResponse(symbol="AAPL", timestamp=_NOW, volume=volume)


def test_volume_spike_detected():
    filtro = Filtro(
        enumFiltro=EnumFiltro.VOLUME_SPIKE,
        parametros=[
            Parametro(
                enumParametro=EnumParametro.CONDICION, etiqueta="",
                objValorSeleccionado=ValorCondicional(
                    enumCondicional=EnumCondicional.MAYOR_QUE,
                    enumTipoValor=EnumTipoValor.CONDICIONAL,
                    valor1=2.0,
                ),
            )
        ],
    )
    strategy = VolumeSpikeStrategy(filtro)
    data = MarketData(
        symbol="AAPL",
        candles=[_candle(1000), _candle(1200), _candle(1100), _candle(5000)],
    )
    assert strategy.evaluate(data)
