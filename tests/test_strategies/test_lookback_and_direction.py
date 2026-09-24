from app.models.enums import EnumFiltro, EnumParametro
from app.models.filtro import Filtro
from app.models.parametro import Parametro
from app.models.valor import ValorInteger, ValorString
from app.scanner.marketdata_models import CandleResponse
from app.scanner.timeframe import bars_requeridas_filtro
from app.strategies.base import MarketData
from app.strategies.momentum import ThroughEMAVWAPAlertStrategy
from app.strategies.patrones import BreakOverRecentHighsLowsStrategy, NewCandleHighLowStrategy


def _candle(index: int, high: float, low: float, close: float) -> CandleResponse:
    return CandleResponse(
        symbol="AAPL", timeframe="M5", timestamp=f"2026-09-23T{14 + index // 60:02d}:{index % 60:02d}:00Z",
        open=close, high=high, low=low, close=close, volume=1000,
    )


def _strategy(cls, enum_filtro, strings=None, integers=None):
    parametros = [Parametro(enumParametro=k, objValorSeleccionado=ValorString(valor=v)) for k, v in (strings or {}).items()]
    parametros += [Parametro(enumParametro=k, objValorSeleccionado=ValorInteger(valor=v)) for k, v in (integers or {}).items()]
    return cls(Filtro(enumFiltro=enum_filtro, parametros=parametros))


def _new_candle(option="HIGH", n=None):
    integers = {EnumParametro.NUMERO_VELAS_NEW_CANDLE: n} if n is not None else None
    return _strategy(NewCandleHighLowStrategy, EnumFiltro.NEW_CANDLE_HIGH_LOW,
                     {EnumParametro.OPCION_EXTREMO_NEW_CANDLE: option}, integers)


def _series_with_old_peak():
    peak = _candle(0, high=50.0, low=9.0, close=10.0)
    quiet = [_candle(i, high=11.0, low=9.0, close=10.0) for i in range(1, 30)]
    breakout = _candle(30, high=12.0, low=9.0, close=11.5)
    return [peak, *quiet, breakout]


def test_new_candle_high_only_looks_at_the_last_n_candles():
    data = MarketData(symbol="AAPL", candles=_series_with_old_peak())

    assert _new_candle(n=20).compute_value(data) == 1.0
    assert _new_candle(n=30).compute_value(data) == 0.0


def test_new_candle_high_needs_n_previous_candles_before_it_can_decide():
    data = MarketData(symbol="AAPL", candles=_series_with_old_peak()[-10:])

    assert _new_candle(n=20).compute_value(data) is None


def test_new_candle_low_uses_the_same_window():
    valley = _candle(0, high=11.0, low=1.0, close=10.0)
    quiet = [_candle(i, high=11.0, low=9.0, close=10.0) for i in range(1, 30)]
    breakdown = _candle(30, high=11.0, low=8.0, close=8.5)
    data = MarketData(symbol="AAPL", candles=[valley, *quiet, breakdown])

    assert _new_candle("LOW", n=20).compute_value(data) == 1.0
    assert _new_candle("LOW", n=30).compute_value(data) == 0.0


def test_break_over_uses_the_configured_number_of_candles():
    strategy = _strategy(BreakOverRecentHighsLowsStrategy, EnumFiltro.BREAK_OVER_RECENT_HIGHS_LOWS,
                         {EnumParametro.OPCION_EXTREMO_BREAK_OVER: "HIGH"},
                         {EnumParametro.NUMERO_VELAS_BREAK_OVER: 20})
    data = MarketData(symbol="AAPL", candles=_series_with_old_peak())

    assert strategy.compute_value(data) == 1.0


def test_the_bars_a_group_asks_for_cover_the_configured_lookback():
    filtro = Filtro(enumFiltro=EnumFiltro.NEW_CANDLE_HIGH_LOW, parametros=[
        Parametro(enumParametro=EnumParametro.NUMERO_VELAS_NEW_CANDLE, objValorSeleccionado=ValorInteger(valor=100))])

    assert bars_requeridas_filtro(filtro, 5) == 101


def _cross_series(direction):
    closes = [10.0] * 30
    closes[-2], closes[-1] = (9.5, 10.6) if direction == "up" else (10.5, 9.4)
    return [_candle(i, high=c + 0.1, low=c - 0.1, close=c) for i, c in enumerate(closes)]


def _through(direction_option):
    return _strategy(ThroughEMAVWAPAlertStrategy, EnumFiltro.THROUGH_EMA_VWAP_ALERT, {
        EnumParametro.THROUGH_EMA_VWAP_LINEA_CRUCE: "EMA",
        EnumParametro.THROUGH_EMA_VWAP_DIRECCION_ROMPIMIENTO: direction_option,
    }, {EnumParametro.THROUGH_EMA_VWAP_PERIODO_EMA: 9})


def test_ema_cross_only_reports_the_chosen_direction():
    up = MarketData(symbol="AAPL", candles=_cross_series("up"))
    down = MarketData(symbol="AAPL", candles=_cross_series("down"))

    assert _through("ABOVE").compute_value(up) > 0
    assert _through("ABOVE").compute_value(down) == 0.0
    assert _through("BELOW").compute_value(down) < 0
    assert _through("BELOW").compute_value(up) == 0.0


def _pullback(option="ALTO", n=None):
    from app.strategies.patrones import PercentagePullbackHighsLowsStrategy
    integers = {EnumParametro.NUMERO_VELAS_PULLBACK: n} if n is not None else None
    return _strategy(PercentagePullbackHighsLowsStrategy, EnumFiltro.PERCENTAGE_PULLBACK_HIGHS_LOWS,
                     {EnumParametro.PUNTO_REFERENCIA_PULLBACK: option}, integers)


def _pullback_series():
    old_peak = _candle(0, high=20.0, low=9.0, close=10.0)
    recent = [_candle(i, high=11.0, low=9.5, close=10.0) for i in range(1, 9)]
    last = _candle(9, high=10.5, low=9.5, close=9.9)
    return [old_peak, *recent, last]


def test_pullback_measures_from_the_high_of_the_configured_window():
    data = MarketData(symbol="AAPL", candles=_pullback_series())

    assert round(_pullback(n=5).compute_value(data), 2) == 10.0
    assert round(_pullback(n=10).compute_value(data), 2) == 50.5


def test_pullback_keeps_five_candles_when_the_parameter_is_missing():
    data = MarketData(symbol="AAPL", candles=_pullback_series())

    assert _pullback().compute_value(data) == _pullback(n=5).compute_value(data)


def test_pullback_needs_the_whole_window():
    data = MarketData(symbol="AAPL", candles=_pullback_series()[-3:])

    assert _pullback(n=5).compute_value(data) is None


def test_pullback_bars_cover_the_configured_window():
    filtro = Filtro(enumFiltro=EnumFiltro.PERCENTAGE_PULLBACK_HIGHS_LOWS, parametros=[
        Parametro(enumParametro=EnumParametro.NUMERO_VELAS_PULLBACK, objValorSeleccionado=ValorInteger(valor=30))])

    assert bars_requeridas_filtro(filtro, 1) == 30
