from app.analysis.indicators import todays_candles
from app.scanner.buffered_candle import BufferedCandle
from app.strategies.base import MarketData


def first_candle_of_day(data: MarketData) -> BufferedCandle | None:
    if data.day is not None:
        return data.day.first
    todays = todays_candles(data.candles)
    return todays[0] if todays else None


def last_close(data: MarketData) -> float | None:
    return data.candles[-1].close if data.candles else None


def day_extremes(data: MarketData) -> tuple[float, float] | None:
    if data.day is not None:
        if data.day.high is None or data.day.low is None:
            return None
        return data.day.high, data.day.low
    todays = todays_candles(data.candles)
    if not todays or any(c.high is None or c.low is None for c in todays):
        return None
    return max(c.high for c in todays), min(c.low for c in todays)
