from app.models.enums import EnumFiltro, EnumParametro
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorString
from app.scanner.marketdata_models import FundamentalResponse, PriceSnapshot
from app.strategies.base import MarketData
from app.strategies.precio_movimiento import ChangeStrategy, GapFromCloseStrategy


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
    snapshot = PriceSnapshot(symbol="AAPL", last=120.0)
    return MarketData(symbol="AAPL", snapshot=snapshot, fundamental=fund)


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


def _gap_filtro() -> Filtro:
    return Filtro(enumFiltro=EnumFiltro.GAP_FROM_CLOSE, parametros=[])


def test_gap_from_close_falls_back_to_premarket_when_regular_open_unset():
    # marketdata-service reports snapshot.open=0.0 (not null) before 9:30 ET
    # -- gap must use the premarket last trade instead of computing against a
    # phantom $0 open (which used to yield a constant -100%).
    snapshot = PriceSnapshot(symbol="AAPL", open=0.0, prevClose=100.0)
    fund = FundamentalResponse(symbol="AAPL", preMarketClose=103.0)
    data = MarketData(symbol="AAPL", snapshot=snapshot, fundamental=fund)
    value = GapFromCloseStrategy(_gap_filtro()).compute_value(data)
    assert value == 3.0


def test_gap_from_close_without_any_open_returns_none():
    snapshot = PriceSnapshot(symbol="AAPL", open=0.0, prevClose=100.0)
    data = MarketData(symbol="AAPL", snapshot=snapshot, fundamental=None)
    assert GapFromCloseStrategy(_gap_filtro()).compute_value(data) is None


def test_gap_from_close_prefers_regular_open_once_available():
    snapshot = PriceSnapshot(symbol="AAPL", open=105.0, prevClose=100.0)
    fund = FundamentalResponse(symbol="AAPL", preMarketClose=999.0)
    data = MarketData(symbol="AAPL", snapshot=snapshot, fundamental=fund)
    value = GapFromCloseStrategy(_gap_filtro()).compute_value(data)
    assert value == 5.0
