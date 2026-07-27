from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData


class BearishBullishEngulfingStrategy(FilterStrategy):
    """Bullish engulfing (close > prev open and open < prev close) or bearish engulfing."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        prev = data.candles[-2]
        curr = data.candles[-1]
        if prev.open is None or prev.close is None or curr.open is None or curr.close is None:
            return None
        tipo = self._param_str(EnumParametro.TIPO_PATRON_BEARISH_BULLISH_ENGULFING_CANDLE, "BULLISH")
        if curr.open < prev.close and curr.close > prev.open:
            return 1.0 if tipo == "BULLISH" else -1.0
        if curr.open > prev.close and curr.close < prev.open:
            return 1.0 if tipo == "BEARISH" else -1.0
        return 0.0


class ConsecutiveCandlesStrategy(FilterStrategy):
    """N consecutive bullish or bearish candles."""

    def compute_value(self, data: MarketData) -> float | None:
        n = self._param_int(EnumParametro.NUMERO_VELAS_CONSECUTIVAS, 3)
        if not data.candles or len(data.candles) < n:
            return None
        recent = data.candles[-n:]
        if any(c.close is None or c.open is None for c in recent):
            return None
        bullish = all(c.close > c.open for c in recent)
        bearish = all(c.close < c.open for c in recent)
        return 1.0 if bullish else (-1.0 if bearish else 0.0)


class FirstCandleStrategy(FilterStrategy):
    """First candle of the day type (bullish/bearish)."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles:
            return None
        first = data.candles[0]
        if first.close is None or first.open is None:
            return None
        return 1.0 if first.close > first.open else (-1.0 if first.close < first.open else 0.0)


class HighLowOfDayStrategy(FilterStrategy):
    """Price near high/low of day."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles:
            return None
        if any(c.high is None or c.low is None for c in data.candles) or data.candles[-1].close is None:
            return None
        day_high = max(c.high for c in data.candles)
        day_low = min(c.low for c in data.candles)
        if day_high <= day_low:
            return 50.0
        price = data.candles[-1].close
        return ((price - day_low) / (day_high - day_low)) * 100.0


class NewCandleHighLowStrategy(FilterStrategy):
    """New N-candle high or low."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        prior = data.candles[:-1]
        curr = data.candles[-1]
        if any(c.high is None or c.low is None for c in prior) or curr.high is None or curr.low is None:
            return None
        prev_high = max(c.high for c in prior)
        prev_low = min(c.low for c in prior)
        if curr.high > prev_high:
            return 1.0
        if curr.low < prev_low:
            return -1.0
        return 0.0


class PercentagePullbackHighsLowsStrategy(FilterStrategy):
    """Percentage pullback from recent high/low."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 5:
            return None
        recent = data.candles[-5:]
        if any(c.high is None for c in recent) or data.candles[-1].close is None:
            return None
        high = max(c.high for c in recent)
        price = data.candles[-1].close
        if high <= 0:
            return None
        return ((high - price) / high) * 100.0


class BreakOverRecentHighsLowsStrategy(FilterStrategy):
    """Price breaking above/below recent N-bar range."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        prior = data.candles[:-1]
        curr = data.candles[-1]
        if any(c.high is None or c.low is None for c in prior) or curr.close is None:
            return None
        prev_high = max(c.high for c in prior)
        prev_low = min(c.low for c in prior)
        if curr.close > prev_high:
            return 1.0
        if curr.close < prev_low:
            return -1.0
        return 0.0


class OpeningRangeBreakdownStrategy(FilterStrategy):
    """Price breaking below opening range."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        first = data.candles[0]
        if first.high is None or first.open is None or first.close is None or first.low is None:
            return None
        if data.candles[-1].close is None:
            return None
        o_range_low = min(first.low, first.open, first.close)
        price = data.candles[-1].close
        if price < o_range_low and o_range_low > 0:
            return 1.0
        return 0.0


class OpeningRangeBreakoutStrategy(FilterStrategy):
    """Price breaking above opening range."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        first = data.candles[0]
        if first.high is None or first.open is None or first.close is None:
            return None
        if data.candles[-1].close is None:
            return None
        o_range_high = max(first.high, first.open, first.close)
        price = data.candles[-1].close
        if price > o_range_high and o_range_high > 0:
            return 1.0
        return 0.0


class PivotsStrategy(FilterStrategy):
    """Price at pivot point (high or low surrounded by lower/higher)."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 3:
            return None
        recent = data.candles[-3:]
        if any(c.high is None or c.low is None for c in recent):
            return None
        h1, h2, h3 = [c.high for c in recent]
        l1, l2, l3 = [c.low for c in recent]
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
