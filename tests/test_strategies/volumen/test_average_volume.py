from datetime import datetime, timezone
from app.models.enums import EnumCondicional, EnumFiltro, EnumParametro, EnumTipoValor
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional, ValorInteger
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


def test_average_volume_uses_only_the_last_n_candles():
    # 25 velas: las primeras 5 (fuera de la ventana default de 20) tienen
    # volumen altisimo -- si entraran al promedio, lo dispararian.
    data = MarketData(symbol="AAPL", candles=[_candle(999999)] * 5 + [_candle(100)] * 20)
    strategy = AverageVolumeStrategy(Filtro(enumFiltro=EnumFiltro.AVERAGE_VOLUME, parametros=[]))
    assert strategy.compute_value(data) == 100.0


def test_numero_velas_parameter_overrides_the_default_window():
    data = MarketData(symbol="AAPL", candles=[_candle(999999)] * 5 + [_candle(100)] * 20)
    filtro = Filtro(
        enumFiltro=EnumFiltro.AVERAGE_VOLUME,
        parametros=[Parametro(
            enumParametro=EnumParametro.NUMERO_VELAS_AVERAGE_VOLUME, etiqueta="",
            objValorSeleccionado=ValorInteger(valor=25),
        )],
    )
    strategy = AverageVolumeStrategy(filtro)
    expected = (999999 * 5 + 100 * 20) / 25
    assert abs(strategy.compute_value(data) - expected) < 1e-6


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
