from app.models.enums import EnumCondicional, EnumFiltro, EnumParametro, EnumTipoValor
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional, ValorString
from app.scanner.marketdata_models import FundamentalResponse
from app.strategies.base import MarketData
from app.strategies.volumen.volumen_post_pre import VolumenPostPreStrategy


def _strategy(tipo: str | None):
    parametros = [
        Parametro(
            enumParametro=EnumParametro.CONDICION,
            etiqueta="",
            objValorSeleccionado=ValorCondicional(
                enumCondicional=EnumCondicional.MAYOR_QUE,
                enumTipoValor=EnumTipoValor.CONDICIONAL,
                valor1=100000.0,
            ),
        )
    ]
    if tipo is not None:
        parametros.append(
            Parametro(
                enumParametro=EnumParametro.TIPO_VOLUMEN,
                etiqueta="",
                objValorSeleccionado=ValorString(valor=tipo),
            )
        )
    return VolumenPostPreStrategy(Filtro(enumFiltro=EnumFiltro.VOLUMEN_POST_PRE, parametros=parametros))


def _data() -> MarketData:
    return MarketData(
        symbol="AAPL",
        fundamental=FundamentalResponse(symbol="AAPL", preMarketVolume=150000.0, postMarketVolume=25000.0),
    )


def test_suma_pre_post_por_defecto_sin_parametro():
    strategy = _strategy(None)
    assert strategy.compute_value(_data()) == 175000.0


def test_ambos_suma_pre_y_post():
    strategy = _strategy("AMBOS")
    assert strategy.compute_value(_data()) == 175000.0


def test_pre_solo_pre_market():
    strategy = _strategy("PRE")
    assert strategy.compute_value(_data()) == 150000.0


def test_post_solo_post_market():
    strategy = _strategy("POST")
    assert strategy.compute_value(_data()) == 25000.0


def test_pre_sin_dato_pre_market_devuelve_none():
    strategy = _strategy("PRE")
    data = MarketData(
        symbol="AAPL",
        fundamental=FundamentalResponse(symbol="AAPL", preMarketVolume=None, postMarketVolume=25000.0),
    )
    assert strategy.compute_value(data) is None


def test_sin_fundamental_devuelve_none():
    strategy = _strategy(None)
    data = MarketData(symbol="AAPL")
    assert strategy.compute_value(data) is None


def test_ambos_cae_a_prev_post_cuando_post_de_hoy_es_cero():
    """postMarketVolume=0 en premarket es un dato real (la sesion de hoy
    todavia no paso), no ausencia -- AMBOS debe usar el postmarket de AYER
    en vez de tratarlo como si valiera 0."""
    strategy = _strategy("AMBOS")
    data = MarketData(
        symbol="AAPL",
        fundamental=FundamentalResponse(
            symbol="AAPL", preMarketVolume=150000.0, postMarketVolume=0, prevPostMarketVolume=40000.0
        ),
    )
    assert strategy.compute_value(data) == 190000.0


def test_ambos_prefiere_post_de_hoy_sobre_prev_post_cuando_ya_hay_dato():
    """Una vez que el post-market de hoy empieza a acumular volumen real, se
    usa ese -- prevPostMarketVolume es solo el fallback para cuando hoy
    todavia esta en 0."""
    strategy = _strategy("AMBOS")
    data = MarketData(
        symbol="AAPL",
        fundamental=FundamentalResponse(
            symbol="AAPL", preMarketVolume=150000.0, postMarketVolume=25000.0, prevPostMarketVolume=999999.0
        ),
    )
    assert strategy.compute_value(data) == 175000.0


def test_ambos_sin_prev_post_ni_post_devuelve_none():
    strategy = _strategy("AMBOS")
    data = MarketData(
        symbol="AAPL",
        fundamental=FundamentalResponse(
            symbol="AAPL", preMarketVolume=150000.0, postMarketVolume=0, prevPostMarketVolume=None
        ),
    )
    assert strategy.compute_value(data) is None
