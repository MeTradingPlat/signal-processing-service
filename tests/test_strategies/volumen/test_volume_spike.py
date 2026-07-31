from datetime import datetime, timezone
from app.models.enums import EnumCondicional, EnumFiltro, EnumParametro, EnumTipoValor
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional, ValorFloat, ValorInteger
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.volumen.volume_spike import VolumeSpikeStrategy

_NOW = datetime.now(timezone.utc)


def _candle(volume: float) -> CandleResponse:
    return CandleResponse(symbol="AAPL", timestamp=_NOW, volume=volume)


def _filtro(n: int, proporcion: float) -> Filtro:
    return Filtro(
        enumFiltro=EnumFiltro.VOLUME_SPIKE,
        parametros=[
            # CONDICION MAYOR_QUE 0: el gate booleano que scanner-management-service
            # genera por defecto para este filtro -- compute_value() ya decide
            # 0.0/1.0 usando NUMERO_VELAS_VOLUME_SPIKE/PROPORCION_VOLUMEN_VOLUME_SPIKE.
            Parametro(enumParametro=EnumParametro.CONDICION, etiqueta="",
                      objValorSeleccionado=ValorCondicional(
                          enumCondicional=EnumCondicional.MAYOR_QUE,
                          enumTipoValor=EnumTipoValor.CONDICIONAL,
                          valor1=0.0,
                      )),
            Parametro(enumParametro=EnumParametro.NUMERO_VELAS_VOLUME_SPIKE, etiqueta="",
                      objValorSeleccionado=ValorInteger(valor=n)),
            Parametro(enumParametro=EnumParametro.PROPORCION_VOLUMEN_VOLUME_SPIKE, etiqueta="",
                      objValorSeleccionado=ValorFloat(valor=proporcion)),
        ],
    )


def test_volume_spike_detected():
    strategy = VolumeSpikeStrategy(_filtro(n=3, proporcion=2.0))
    data = MarketData(
        symbol="AAPL",
        candles=[_candle(1000), _candle(1200), _candle(1100), _candle(5000)],
    )
    assert strategy.evaluate(data)


def test_volume_spike_not_detected_below_proporcion():
    strategy = VolumeSpikeStrategy(_filtro(n=3, proporcion=2.0))
    data = MarketData(
        symbol="AAPL",
        candles=[_candle(1000), _candle(1200), _candle(1100), _candle(1300)],
    )
    assert not strategy.evaluate(data)


def test_volume_spike_ignores_bars_outside_configured_window():
    strategy = VolumeSpikeStrategy(_filtro(n=2, proporcion=2.0))
    data = MarketData(
        symbol="AAPL",
        # La vela vieja de 10000 quedaria fuera de la ventana de 2 velas --
        # si se colara igual, el promedio previo se inflaria y el spike no
        # se detectaria.
        candles=[_candle(10000), _candle(100), _candle(100), _candle(250)],
    )
    assert strategy.evaluate(data)
