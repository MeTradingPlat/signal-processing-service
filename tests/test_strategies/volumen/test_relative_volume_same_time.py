from datetime import datetime, timedelta, timezone
from app.models.enums import EnumFiltro
from app.models.filtro import Filtro
from app.scanner.marketdata_models import CandleResponse
from app.strategies.base import MarketData
from app.strategies.volumen.relative_volume_same_time import RelativeVolumeSameTimeStrategy

_BASE_DAY = datetime(2026, 7, 20, tzinfo=timezone.utc)


def _candle(day_offset: int, hour: int, minute: int, volume: float) -> CandleResponse:
    ts = _BASE_DAY.replace(hour=hour, minute=minute) - timedelta(days=day_offset)
    return CandleResponse(symbol="AAPL", timestamp=ts, volume=volume)


def _strategy() -> RelativeVolumeSameTimeStrategy:
    return RelativeVolumeSameTimeStrategy(Filtro(enumFiltro=EnumFiltro.RELATIVE_VOLUME_SAME_TIME))


def test_only_matches_candles_at_the_exact_same_time_of_day():
    candles = []
    for d in range(1, 7):
        candles.append(_candle(d, 14, 30, 100))
        candles.append(_candle(d, 15, 0, 99999))  # otra hora, no debe contar
    candles.append(_candle(0, 14, 30, 300))
    data = MarketData(symbol="AAPL", candles=candles)
    assert _strategy().compute_value(data) == 300.0


def test_caps_comparison_to_five_previous_days():
    candles = [_candle(d, 14, 30, 100) for d in range(1, 10)]
    candles.append(_candle(0, 14, 30, 500))
    data = MarketData(symbol="AAPL", candles=candles)
    # Con 5 dias de referencia a 100 cada uno, promedio=100 -> 500/100=500%
    assert _strategy().compute_value(data) == 500.0


def test_no_matching_prior_day_returns_none():
    candles = [_candle(1, 9, 0, 100), _candle(0, 14, 30, 300)]
    data = MarketData(symbol="AAPL", candles=candles)
    assert _strategy().compute_value(data) is None
