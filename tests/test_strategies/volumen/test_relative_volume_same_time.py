from datetime import datetime, timedelta, timezone
from app.models.enums import EnumFiltro, EnumParametro
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorInteger
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.volumen.relative_volume_same_time import RelativeVolumeSameTimeStrategy

_BASE_DAY = datetime(2026, 7, 20, tzinfo=timezone.utc)


def _candle(day_offset: int, hour: int, minute: int, volume: float) -> CandleResponse:
    ts = _BASE_DAY.replace(hour=hour, minute=minute) - timedelta(days=day_offset)
    return CandleResponse(symbol="AAPL", timestamp=ts, volume=volume)


def _strategy(numero_dias: int | None = None) -> RelativeVolumeSameTimeStrategy:
    parametros = []
    if numero_dias is not None:
        parametros.append(Parametro(
            enumParametro=EnumParametro.NUMERO_DIAS_RELATIVE_VOLUME_SAME_TIME, etiqueta="",
            objValorSeleccionado=ValorInteger(valor=numero_dias),
        ))
    return RelativeVolumeSameTimeStrategy(
        Filtro(enumFiltro=EnumFiltro.RELATIVE_VOLUME_SAME_TIME, parametros=parametros))


def test_only_matches_candles_at_the_exact_same_time_of_day():
    candles = []
    for d in range(1, 7):
        candles.append(_candle(d, 14, 30, 100))
        candles.append(_candle(d, 15, 0, 99999))  # otra hora, no debe contar
    candles.append(_candle(0, 14, 30, 300))
    data = MarketData(symbol="AAPL", candles=candles)
    assert _strategy().compute_value(data) == 300.0


def test_caps_comparison_to_default_ten_previous_days():
    # Orden cronologico real (mas viejo primero): el dia mas viejo (offset 11)
    # tiene un volumen muy distinto (999999) que NO debe entrar en el
    # promedio si el cap de 10 dias (default) se respeta -- solo cuentan los
    # 10 mas recientes (offsets 10-1, volumen 100 cada uno).
    candles = [_candle(11, 14, 30, 999999)]
    candles += [_candle(d, 14, 30, 100) for d in range(10, 0, -1)]
    candles.append(_candle(0, 14, 30, 500))
    data = MarketData(symbol="AAPL", candles=candles)
    assert _strategy().compute_value(data) == 500.0


def test_numero_dias_parameter_overrides_the_default():
    # Orden cronologico real (mas viejo primero, como llega el buffer de
    # produccion): los 7 dias mas viejos (offsets 10-4) tienen volumen 200,
    # los 3 mas recientes (offsets 3-1) tienen volumen 50 -- una ventana mas
    # corta debe dar un promedio distinto a la ventana default de 10.
    candles = [_candle(d, 14, 30, 200) for d in range(10, 3, -1)]
    candles += [_candle(d, 14, 30, 50) for d in range(3, 0, -1)]
    candles.append(_candle(0, 14, 30, 100))
    data = MarketData(symbol="AAPL", candles=candles)

    # NUMERO_DIAS=3: solo los 3 mas recientes (50 cada uno) -> 100/50=200%
    assert _strategy(numero_dias=3).compute_value(data) == 200.0
    # Default (10 dias): promedio de los 10 -> (7*200 + 3*50)/10 = 155
    assert abs(_strategy().compute_value(data) - (100 / 155 * 100.0)) < 1e-9


def test_no_matching_prior_day_returns_none():
    candles = [_candle(1, 9, 0, 100), _candle(0, 14, 30, 300)]
    data = MarketData(symbol="AAPL", candles=candles)
    assert _strategy().compute_value(data) is None
