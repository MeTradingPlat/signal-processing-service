from datetime import datetime, timezone
from app.models.enums import EnumFiltro, EnumParametro
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorString
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.patrones import FirstCandleStrategy

_TODAY = datetime.now(timezone.utc)


def _candle(open_: float, close: float) -> CandleResponse:
    return CandleResponse(symbol="AAPL", timestamp=_TODAY, open=open_, close=close)


def _filtro(tipo: str) -> Filtro:
    return Filtro(
        enumFiltro=EnumFiltro.FIRST_CANDLE,
        parametros=[
            Parametro(enumParametro=EnumParametro.TIPO_VELA_FIRTS_CANDLE, etiqueta="",
                      objValorSeleccionado=ValorString(valor=tipo)),
        ],
    )


def test_bullish_first_candle_matches_alcista():
    strategy = FirstCandleStrategy(_filtro("ALCISTA"))
    data = MarketData(symbol="AAPL", candles=[_candle(open_=10, close=11)])
    assert strategy.compute_value(data) == 1.0


def test_bearish_first_candle_does_not_match_alcista():
    strategy = FirstCandleStrategy(_filtro("ALCISTA"))
    data = MarketData(symbol="AAPL", candles=[_candle(open_=11, close=10)])
    assert strategy.compute_value(data) == -1.0


def test_bearish_first_candle_matches_bajista():
    strategy = FirstCandleStrategy(_filtro("BAJISTA"))
    data = MarketData(symbol="AAPL", candles=[_candle(open_=11, close=10)])
    assert strategy.compute_value(data) == 1.0
