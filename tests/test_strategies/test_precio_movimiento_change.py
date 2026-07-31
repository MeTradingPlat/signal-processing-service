from app.models.enums import EnumFiltro, EnumParametro
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorString
from app.scanner.marketdata_models import FundamentalResponse, QuoteResponse
from app.strategies.base import MarketData
from app.strategies.precio_movimiento import ChangeStrategy


def _filtro(punto_referencia: str) -> Filtro:
    return Filtro(
        enumFiltro=EnumFiltro.CHANGE,
        parametros=[
            Parametro(enumParametro=EnumParametro.PUNTO_REFERENCIA_CHANGE, etiqueta="",
                      objValorSeleccionado=ValorString(valor=punto_referencia)),
            Parametro(enumParametro=EnumParametro.TIPO_MEDIDA_CHANGE, etiqueta="",
                      objValorSeleccionado=ValorString(valor="PORCENTAJE")),
        ],
    )


def _data(pre_market_close=None, post_market_close=None) -> MarketData:
    fund = FundamentalResponse(symbol="AAPL", preMarketClose=pre_market_close, postMarketClose=post_market_close)
    quote = QuoteResponse(symbol="AAPL", last=120.0)
    return MarketData(symbol="AAPL", quote=quote, fundamental=fund)


def test_close_pre_market_reference():
    data = _data(pre_market_close=100.0)
    value = ChangeStrategy(_filtro("CLOSE_PRE_MARKET")).compute_value(data)
    assert value == 20.0


def test_close_post_market_reference():
    data = _data(post_market_close=110.0)
    value = ChangeStrategy(_filtro("CLOSE_POST_MARKET")).compute_value(data)
    assert abs(value - 9.090909090909092) < 1e-9


def test_close_pre_market_without_data_returns_none_not_wrong_value():
    data = _data()
    assert ChangeStrategy(_filtro("CLOSE_PRE_MARKET")).compute_value(data) is None


def test_close_post_market_without_data_returns_none_not_wrong_value():
    data = _data()
    assert ChangeStrategy(_filtro("CLOSE_POST_MARKET")).compute_value(data) is None
