from app.models.enums import EnumParametro
from app.scanner.marketdata_models import CandleResponse, FundamentalResponse, QuoteResponse
from app.strategies.base import FilterStrategy, MarketData


class PrecioStrategy(FilterStrategy):
    """Current price vs threshold."""

    def compute_value(self, data: MarketData) -> float:
        if data.quote and data.quote.last:
            return data.quote.last
        if data.fundamental and data.fundamental.open:
            return data.fundamental.open
        return 0.0


class ChangeStrategy(FilterStrategy):
    """Price change since a reference point (open/prevClose)."""

    def compute_value(self, data: MarketData) -> float:
        ref = self._param_str(EnumParametro.PUNTO_REFERENCIA_CHANGE, "CLOSE")
        medida = self._param_str(EnumParametro.TIPO_MEDIDA_CHANGE, "PRECIO")
        current = None
        reference = None
        if data.quote:
            current = getattr(data.quote, "last", None)
            if ref == "OPEN":
                reference = getattr(data.quote, "open", None)
            elif ref in ("CLOSE", "PREV_CLOSE"):
                reference = getattr(data.quote, "prevClose", None)
        if current is None and data.fundamental:
            current = data.fundamental.open
            reference = data.fundamental.prevClose
        if not current or not reference or reference == 0:
            return 0.0
        diff = current - reference
        return diff if medida == "PRECIO" else (diff / reference) * 100.0


class PercentageChangeStrategy(FilterStrategy):
    """Percentage change over N candles."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        first_open = data.candles[0].open or 0.0
        last_close = data.candles[-1].close or 0.0
        if first_open <= 0:
            return 0.0
        return ((last_close - first_open) / first_open) * 100.0


class GapFromCloseStrategy(FilterStrategy):
    """Gap between current open and previous close, in % or price."""

    def compute_value(self, data: MarketData) -> float:
        formato = self._param_str(EnumParametro.FORMATO_GAP_FROM_CLOSE, "PORCENTAJE")
        current_open = None
        prev_close = None
        if data.quote:
            current_open = data.quote.open
            prev_close = data.quote.prevClose
        if current_open is None and data.fundamental:
            current_open = data.fundamental.open
            prev_close = data.fundamental.prevClose
        if not current_open or not prev_close or prev_close <= 0:
            return 0.0
        gap = current_open - prev_close
        return (gap / prev_close) * 100.0 if formato == "PORCENTAJE" else gap


class PositionInRangeStrategy(FilterStrategy):
    """Position of current price within day's range (0-100%)."""

    def compute_value(self, data: MarketData) -> float:
        q = data.quote
        if not q or not q.high or not q.low or q.high <= q.low:
            return 50.0
        price = q.last or q.close or 0.0
        return ((price - q.low) / (q.high - q.low)) * 100.0


class PercentageRangeStrategy(FilterStrategy):
    """Day's range as percentage of price."""

    def compute_value(self, data: MarketData) -> float:
        q = data.quote
        if not q or not q.high or not q.low:
            return 0.0
        mid = (q.high + q.low) / 2.0
        if mid <= 0:
            return 0.0
        return ((q.high - q.low) / mid) * 100.0


class RangeDollarsStrategy(FilterStrategy):
    """Day's range in dollars."""

    def compute_value(self, data: MarketData) -> float:
        q = data.quote
        if not q or not q.high or not q.low:
            return 0.0
        return q.high - q.low


class CrossingAboveBelowStrategy(FilterStrategy):
    """Price crossing above/below EMA level."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        periodo = self._param_int(EnumParametro.PERIODO_EMA_CROSSING_ABOVE_BELOW, 9)
        candles_needed = min(len(data.candles), periodo + 1)
        recent = data.candles[-candles_needed:]
        closes = [c.close or 0.0 for c in recent]
        ema = _calc_ema(closes, periodo)
        if ema <= 0:
            return 0.0
        current = closes[-1]
        prev_close_val = closes[-2] if len(closes) >= 2 else current
        return ((current / ema) - 1.0) * 100.0


class HaltStrategy(FilterStrategy):
    """Whether trading is halted."""

    def compute_value(self, data: MarketData) -> float:
        if data.quote and data.quote.tradingHalted:
            return 1.0
        if data.fundamental and data.fundamental.tradingStatus:
            status = data.fundamental.tradingStatus
            if status.upper() not in ("ACTIVE", ""):
                return 1.0
        return 0.0


def _calc_ema(values: list[float], period: int) -> float:
    if len(values) < period:
        period = len(values)
    if period == 0:
        return 0.0
    multiplier = 2.0 / (period + 1.0)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v - ema) * multiplier + ema
    return ema


def _calc_sma(values: list[float], period: int) -> float:
    if len(values) < period:
        period = len(values)
    return sum(values[-period:]) / period if period > 0 else 0.0


def _calc_atr(candles: list[CandleResponse], period: int) -> float:
    """Wilder's ATR: initial SMA then smoothed (Prior ATR * (N-1) + TR) / N"""
    if len(candles) < 2:
        return 0.0
    tr_values = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i - 1]
        h = c.high or 0.0
        l = c.low or 0.0
        pc = prev.close or 0.0
        tr_values.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not tr_values:
        return 0.0
    if len(tr_values) <= period:
        return sum(tr_values) / len(tr_values)
    atr = sum(tr_values[:period]) / period
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period
    return atr


def _calc_rsi(candles: list[CandleResponse], period: int) -> float:
    """Wilder's RSI: initial SMA then smoothed avg gain/loss"""
    if len(candles) < period + 1:
        return 50.0
    closes = [(c.close or 0.0) for c in candles]
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]
    if not gains and not losses:
        return 50.0
    if len(changes) <= period:
        avg_gain = sum(gains) / len(changes) if gains else 0.0
        avg_loss = sum(losses) / len(changes) if losses else 0.0
    else:
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(changes)):
            g = changes[i] if changes[i] > 0 else 0.0
            l = -changes[i] if changes[i] < 0 else 0.0
            avg_gain = (avg_gain * (period - 1) + g) / period
            avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _calc_vwap(candles: list[CandleResponse]) -> float:
    """VWAP: Σ(TypicalPrice × Volume) / Σ(Volume). Resets daily (only today's candles)."""
    if not candles:
        return 0.0
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()
    tv = 0.0
    tp = 0.0
    for c in candles:
        if c.timestamp and c.timestamp.date() != today:
            continue
        typical = ((c.high or 0.0) + (c.low or 0.0) + (c.close or 0.0)) / 3.0
        vol = c.volume or 0.0
        tv += typical * vol
        tp += vol
    if tp <= 0:
        recent = [c for c in candles if c.timestamp and c.timestamp.date() == today]
        if not recent:
            recent = candles[-max(1, len(candles) // 10):]
        for c in recent:
            typical = ((c.high or 0.0) + (c.low or 0.0) + (c.close or 0.0)) / 3.0
            vol = c.volume or 0.0
            tv += typical * vol
            tp += vol
    return tv / tp if tp > 0 else 0.0
