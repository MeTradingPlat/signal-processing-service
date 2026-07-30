from app.models.enums import EnumParametro
from app.scanner.marketdata_models import CandleResponse, FundamentalResponse, QuoteResponse
from app.strategies.base import FilterStrategy, MarketData


class PrecioStrategy(FilterStrategy):
    """Current price vs threshold."""

    def compute_value(self, data: MarketData) -> float | None:
        if data.quote and data.quote.last is not None:
            return data.quote.last
        if data.fundamental and data.fundamental.open is not None:
            return data.fundamental.open
        return None


class ChangeStrategy(FilterStrategy):
    """Price change since a reference point (open/prevClose)."""

    def compute_value(self, data: MarketData) -> float | None:
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
        if current is None or reference is None or reference == 0:
            return None
        diff = current - reference
        return diff if medida == "PRECIO" else (diff / reference) * 100.0


class PercentageChangeStrategy(FilterStrategy):
    """Percentage change over N candles."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        first_open = data.candles[0].open
        last_close = data.candles[-1].close
        if first_open is None or last_close is None or first_open <= 0:
            return None
        return ((last_close - first_open) / first_open) * 100.0


class GapFromCloseStrategy(FilterStrategy):
    """Gap between current open and previous close, in % or price."""

    def compute_value(self, data: MarketData) -> float | None:
        formato = self._param_str(EnumParametro.FORMATO_GAP_FROM_CLOSE, "PORCENTAJE")
        current_open = None
        prev_close = None
        if data.quote:
            current_open = data.quote.open
            prev_close = data.quote.prevClose
        if current_open is None and data.fundamental:
            current_open = data.fundamental.open
            prev_close = data.fundamental.prevClose
        if current_open is None or prev_close is None or prev_close <= 0:
            return None
        gap = current_open - prev_close
        return (gap / prev_close) * 100.0 if formato == "PORCENTAJE" else gap


class PositionInRangeStrategy(FilterStrategy):
    """Position of current price within day's range (0-100%)."""

    def compute_value(self, data: MarketData) -> float | None:
        q = data.quote
        if not q or q.high is None or q.low is None:
            return None
        if q.high <= q.low:
            return 50.0
        price = q.last if q.last is not None else q.close
        if price is None:
            return None
        return ((price - q.low) / (q.high - q.low)) * 100.0


class PercentageRangeStrategy(FilterStrategy):
    """Day's range as percentage of price."""

    def compute_value(self, data: MarketData) -> float | None:
        q = data.quote
        if not q or q.high is None or q.low is None:
            return None
        mid = (q.high + q.low) / 2.0
        if mid <= 0:
            return None
        return ((q.high - q.low) / mid) * 100.0


class RangeDollarsStrategy(FilterStrategy):
    """Day's range in dollars."""

    def compute_value(self, data: MarketData) -> float | None:
        q = data.quote
        if not q or q.high is None or q.low is None:
            return None
        return q.high - q.low


class CrossingAboveBelowStrategy(FilterStrategy):
    """Price actually crossing above/below the EMA this bar -- el cierre
    previo estaba a un lado de la EMA y el actual quedo del otro. Mismo bug
    que ThroughEMAVWAPAlertStrategy (momentum.py): solo calculaba la
    distancia actual, identico a estar simplemente cerca de la linea, sin
    comparar contra la vela anterior para confirmar un cruce real."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        periodo = self._param_int(EnumParametro.PERIODO_EMA_CROSSING_ABOVE_BELOW, 9)
        candles_needed = min(len(data.candles), periodo + 1)
        recent = data.candles[-candles_needed:]
        if any(c.close is None for c in recent):
            return None
        closes = [c.close for c in recent]
        ema = _calc_ema(closes, periodo)
        if ema <= 0:
            return None
        prev_close, curr_close = closes[-2], closes[-1]
        crossed_up = prev_close <= ema < curr_close
        crossed_down = prev_close >= ema > curr_close
        if not (crossed_up or crossed_down):
            return 0.0
        return ((curr_close / ema) - 1.0) * 100.0


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


def _calc_atr(candles: list[CandleResponse], period: int) -> float | None:
    """Wilder's ATR: initial SMA then smoothed (Prior ATR * (N-1) + TR) / N"""
    if len(candles) < 2:
        return None
    tr_values = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i - 1]
        if c.high is None or c.low is None or prev.close is None:
            return None
        tr_values.append(max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close)))
    if not tr_values:
        return None
    if len(tr_values) <= period:
        return sum(tr_values) / len(tr_values)
    atr = sum(tr_values[:period]) / period
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period
    return atr


def _calc_rsi(candles: list[CandleResponse], period: int) -> float | None:
    """Wilder's RSI: initial SMA then smoothed avg gain/loss"""
    if len(candles) < period + 1:
        return None
    if any(c.close is None for c in candles):
        return None
    closes = [c.close for c in candles]
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


def _calc_vwap(candles: list[CandleResponse]) -> float | None:
    """VWAP: Σ(TypicalPrice × Volume) / Σ(Volume). Resets daily (only today's candles).
    Bars missing high/low/close/volume are skipped rather than aborting the whole
    calculation, since this is a plain weighted sum, not an order-dependent series."""
    if not candles:
        return None

    def _accumulate(bars: list[CandleResponse]) -> tuple[float, float]:
        tv = tp = 0.0
        for c in bars:
            if c.high is None or c.low is None or c.close is None or c.volume is None:
                continue
            typical = (c.high + c.low + c.close) / 3.0
            tv += typical * c.volume
            tp += c.volume
        return tv, tp

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()
    todays = [c for c in candles if c.timestamp and c.timestamp.date() == today]

    tv, tp = _accumulate(todays)
    if tp <= 0:
        fallback = todays if todays else candles[-max(1, len(candles) // 10):]
        tv, tp = _accumulate(fallback)
    return tv / tp if tp > 0 else None
