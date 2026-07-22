from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData
from app.strategies.precio_movimiento import _calc_sma


class BearishBullishEngulfingStrategy(FilterStrategy):
    """Bullish engulfing (close > prev open and open < prev close) or bearish engulfing."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        prev = data.candles[-2]
        curr = data.candles[-1]
        tipo = self._param_str(EnumParametro.TIPO_PATRON_BEARISH_BULLISH_ENGULFING_CANDLE, "BULLISH")
        o1, c1 = prev.open or 0.0, prev.close or 0.0
        o2, c2 = curr.open or 0.0, curr.close or 0.0
        if o2 < c1 and c2 > o1:
            return 1.0 if tipo == "BULLISH" else -1.0
        if o2 > c1 and c2 < o1:
            return 1.0 if tipo == "BEARISH" else -1.0
        return 0.0


class ConsecutiveCandlesStrategy(FilterStrategy):
    """N consecutive bullish or bearish candles."""

    def compute_value(self, data: MarketData) -> float:
        n = self._param_int(EnumParametro.NUMERO_VELAS_CONSECUTIVAS, 3)
        if not data.candles or len(data.candles) < n:
            return 0.0
        recent = data.candles[-n:]
        bullish = all((c.close or 0.0) > (c.open or 0.0) for c in recent)
        bearish = all((c.close or 0.0) < (c.open or 0.0) for c in recent)
        return 1.0 if bullish else (-1.0 if bearish else 0.0)


class FirstCandleStrategy(FilterStrategy):
    """First candle of the day type (bullish/bearish)."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 1:
            return 0.0
        first = data.candles[0]
        c = first.close or 0.0
        o = first.open or 0.0
        return 1.0 if c > o else (-1.0 if c < o else 0.0)


class HighLowOfDayStrategy(FilterStrategy):
    """Price near high/low of day."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 1:
            return 50.0
        all_highs = [c.high or 0.0 for c in data.candles]
        all_lows = [c.low or float("inf") for c in data.candles]
        day_high = max(all_highs)
        day_low = min(all_lows)
        if day_high <= day_low:
            return 50.0
        price = data.candles[-1].close or 0.0
        return ((price - day_low) / (day_high - day_low)) * 100.0


class NewCandleHighLowStrategy(FilterStrategy):
    """New N-candle high or low."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        prev_high = max(c.high or 0.0 for c in data.candles[:-1])
        prev_low = min(c.low or float("inf") for c in data.candles[:-1])
        curr = data.candles[-1]
        if (curr.high or 0.0) > prev_high:
            return 1.0
        if (curr.low or float("inf")) < prev_low:
            return -1.0
        return 0.0


class PercentagePullbackHighsLowsStrategy(FilterStrategy):
    """Percentage pullback from recent high/low."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 5:
            return 0.0
        recent = data.candles[-5:]
        high = max(c.high or 0.0 for c in recent)
        price = data.candles[-1].close or 0.0
        if high <= 0:
            return 0.0
        return ((high - price) / high) * 100.0


class BreakOverRecentHighsLowsStrategy(FilterStrategy):
    """Price breaking above/below recent N-bar range."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        prev_high = max(c.high or 0.0 for c in data.candles[:-1])
        prev_low = min(c.low or float("inf") for c in data.candles[:-1])
        curr = data.candles[-1]
        if (curr.close or 0.0) > prev_high:
            return 1.0
        if (curr.close or 0.0) < prev_low:
            return -1.0
        return 0.0


class OpeningRangeBreakdownStrategy(FilterStrategy):
    """Price breaking below opening range."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        first = data.candles[0]
        o_range_high = max(first.high or 0.0, first.open or 0.0, first.close or 0.0)
        o_range_low = min(first.low or 0.0, first.open or 0.0, first.close or 0.0)
        price = data.candles[-1].close or 0.0
        if price < o_range_low and o_range_low > 0:
            return 1.0
        return 0.0


class OpeningRangeBreakoutStrategy(FilterStrategy):
    """Price breaking above opening range."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        first = data.candles[0]
        o_range_high = max(first.high or 0.0, first.open or 0.0, first.close or 0.0)
        price = data.candles[-1].close or 0.0
        if price > o_range_high and o_range_high > 0:
            return 1.0
        return 0.0


class PivotsStrategy(FilterStrategy):
    """Price at pivot point (high or low surrounded by lower/higher)."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 3:
            return 0.0
        recent = data.candles[-3:]
        h1, h2, h3 = [c.high or 0.0 for c in recent]
        l1, l2, l3 = [c.low or 0.0 for c in recent]
        if h2 > h1 and h2 > h3:
            return 1.0
        if l2 < l1 and l2 < l3:
            return -1.0
        return 0.0


class MinutosInMarketStrategy(FilterStrategy):
    """Minutes since market open."""

    def compute_value(self, data: MarketData) -> float:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        minutes = now.hour * 60 + now.minute
        market_open = 9 * 60 + 30
        return float(max(0, minutes - market_open))
