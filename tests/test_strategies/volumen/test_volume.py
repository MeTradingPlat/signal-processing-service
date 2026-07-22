from app.models.enums import EnumCondicional, EnumFiltro, EnumParametro, EnumTipoValor
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional
from app.scanner.marketdata_models import QuoteResponse
from app.strategies.base import MarketData
from app.strategies.volumen.volume import VolumeStrategy


def test_volume_from_quote():
    filtro = Filtro(
        enumFiltro=EnumFiltro.VOLUME,
        parametros=[
            Parametro(
                enumParametro=EnumParametro.CONDICION,
                etiqueta="",
                objValorSeleccionado=ValorCondicional(
                    enumCondicional=EnumCondicional.MAYOR_QUE,
                    enumTipoValor=EnumTipoValor.CONDICIONAL,
                    valor1=100000.0,
                ),
            )
        ],
    )
    strategy = VolumeStrategy(filtro)
    data = MarketData(symbol="AAPL", quote=QuoteResponse(symbol="AAPL", volume=200000.0))
    assert strategy.evaluate(data)
