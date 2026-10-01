from datetime import datetime, timezone

from app.models.enums import EnumCondicional, EnumFiltro, EnumParametro, EnumTipoValor
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional, ValorInteger
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


def test_relative_volume_uses_only_the_last_n_previous_candles():
    # 25 velas previas: las primeras 5 (fuera de la ventana default de 20)
    # tienen volumen altisimo -- si entraran al promedio, lo dispararian y
    # el relativo daria mucho mas bajo de lo real.
    candles = [_candle(999999)] * 5 + [_candle(100)] * 20 + [_candle(300)]
    data = MarketData(symbol="AAPL", candles=candles)
    strategy = _strategy(EnumCondicional.MAYOR_QUE, 0.0)
    assert strategy.compute_value(data) == 300.0


def test_numero_velas_parameter_overrides_the_default_window():
    candles = [_candle(999999)] * 5 + [_candle(100)] * 20 + [_candle(300)]
    data = MarketData(symbol="AAPL", candles=candles)
    filtro = Filtro(
        enumFiltro=EnumFiltro.RELATIVE_VOLUME,
        parametros=[Parametro(
            enumParametro=EnumParametro.NUMERO_VELAS_RELATIVE_VOLUME, etiqueta="",
            objValorSeleccionado=ValorInteger(valor=25),
        )],
    )
    expected_avg = (999999 * 5 + 100 * 20) / 25
    assert abs(RelativeVolumeStrategy(filtro).compute_value(data) - (300 / expected_avg * 100.0)) < 1e-6


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
