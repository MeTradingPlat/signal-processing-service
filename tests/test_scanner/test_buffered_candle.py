import pytest

from app.scanner.buffered_candle import BufferedCandle, candle_from_bar


def test_candle_from_bar_expone_los_campos_que_leen_las_estrategias():
    candle = candle_from_bar("AAPL", {"time": 1_700_000_000, "open": 1, "high": 3, "low": 0.5, "close": 2, "volume": 100})

    assert (candle.symbol, candle.open, candle.high, candle.low, candle.close, candle.volume) == ("AAPL", 1, 3, 0.5, 2, 100)
    assert candle.timestamp.tzinfo is not None
    assert candle.vwap is None


def test_bar_sin_precios_deja_none():
    candle = candle_from_bar("AAPL", {"time": 1_700_000_000})

    assert candle.close is None


def test_no_tiene_dict_por_instancia():
    candle = candle_from_bar("AAPL", {"time": 1_700_000_000})

    with pytest.raises(AttributeError):
        candle.extra = 1
    assert not hasattr(candle, "__dict__")
    assert isinstance(candle, BufferedCandle)
