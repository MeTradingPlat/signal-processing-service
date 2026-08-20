from app.models.enums import EnumParametro
from app.scanner.marketdata_models import CandleResponse, FundamentalResponse, PriceSnapshot
from app.strategies.base import FilterStrategy, MarketData
from app.strategies.patrones import _todays_candles


class PrecioStrategy(FilterStrategy):
    """Current price vs threshold."""

    def compute_value(self, data: MarketData) -> float | None:
        if data.snapshot and data.snapshot.last is not None:
            return data.snapshot.last
        if data.fundamental and data.fundamental.open is not None:
            return data.fundamental.open
        return None


class ChangeStrategy(FilterStrategy):
    """Price change since a reference point -- PUNTO_REFERENCIA_CHANGE elige
    el punto: OPEN (apertura de hoy), CLOSE (cierre del dia anterior),
    CLOSE_PRE_MARKET/CLOSE_POST_MARKET (ultimo precio operado en pre/post
    market hoy). Las ultimas dos antes no se manejaban -- devolvian None
    siempre (excluian el simbolo sin aviso) porque no existia ningun dato de
    precio pre/post market en el sistema; ahora vienen de
    FundamentalResponse.preMarketClose/postMarketClose (capturados via el
    evento TradeETH de DxLink en marketdata-service)."""

    def compute_value(self, data: MarketData) -> float | None:
        ref = self._param_str(EnumParametro.PUNTO_REFERENCIA_CHANGE, "CLOSE")
        medida = self._param_str(EnumParametro.TIPO_MEDIDA_CHANGE, "PRECIO")
        current = data.snapshot.last if data.snapshot else None
        if current is None and data.fundamental:
            current = data.fundamental.open

        reference = None
        if ref == "OPEN":
            reference = data.snapshot.open if data.snapshot else None
            if not reference and data.fundamental:
                reference = data.fundamental.open
        elif ref == "CLOSE":
            reference = data.snapshot.prevClose if data.snapshot else None
            if reference is None and data.fundamental:
                reference = data.fundamental.prevClose
        elif ref == "CLOSE_PRE_MARKET":
            reference = data.fundamental.preMarketClose if data.fundamental else None
        elif ref == "CLOSE_POST_MARKET":
            reference = data.fundamental.postMarketClose if data.fundamental else None

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
    """Gap between current price and previous close, in % or price.

    "Current price" prefers today's regular-session open once it exists, but
    before 9:30 ET marketdata-service reports it as 0 (IntradaySnapshot.Open
    is a bare float64, not a pointer -- it only gets set once a regular-
    session M1 candle closes), not null. `current_open is None` never caught
    that, so every premarket scan computed gap against a phantom $0 open
    (-100% every time) instead of falling back -- a "Gap and Go" filter run
    in premarket could never fire. Falls back through fundamentals and
    finally to the premarket last trade, which is what "gap" means to a
    trader scanning before the open."""

    def compute_value(self, data: MarketData) -> float | None:
        formato = self._param_str(EnumParametro.FORMATO_GAP_FROM_CLOSE, "PORCENTAJE")
        current_open = data.snapshot.open if data.snapshot else None
        prev_close = data.snapshot.prevClose if data.snapshot else None
        if not current_open and data.fundamental:
            current_open = data.fundamental.open or data.fundamental.preMarketClose
        if prev_close is None and data.fundamental:
            prev_close = data.fundamental.prevClose
        if not current_open or prev_close is None or prev_close <= 0:
            return None
        gap = current_open - prev_close
        return (gap / prev_close) * 100.0 if formato == "PORCENTAJE" else gap


class PositionInRangeStrategy(FilterStrategy):
    """Position of current price within day's range (0-100%)."""

    def compute_value(self, data: MarketData) -> float | None:
        q = data.snapshot
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
        q = data.snapshot
        if not q or q.high is None or q.low is None:
            return None
        mid = (q.high + q.low) / 2.0
        if mid <= 0:
            return None
        return ((q.high - q.low) / mid) * 100.0


class RangeDollarsStrategy(FilterStrategy):
    """Day's range in dollars."""

    def compute_value(self, data: MarketData) -> float | None:
        q = data.snapshot
        if not q or q.high is None or q.low is None:
            return None
        return q.high - q.low


class CrossingAboveBelowStrategy(FilterStrategy):
    """Price actually crossing above/below a reference level this bar -- el
    cierre previo estaba a un lado del nivel y el actual quedo del otro.
    NIVEL_CRUCE elige el nivel (antes se ignoraba y siempre usaba EMA):
    OPEN = apertura de hoy, CLOSE = cierre del dia anterior, VWAP, o EMA
    (default). Mismo bug que ThroughEMAVWAPAlertStrategy (momentum.py): solo
    calculaba la distancia actual, identico a estar simplemente cerca de la
    linea, sin comparar contra la vela anterior para confirmar un cruce
    real."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        nivel = self._param_str(EnumParametro.NIVEL_CRUCE_CROSSING_ABOVE_BELOW, "EMA")
        if nivel == "VWAP":
            ref = _calc_vwap(data.candles)
            closes = [c.close for c in data.candles[-2:]]
            if any(c is None for c in closes):
                return None
        elif nivel == "OPEN":
            todays = _todays_candles(data.candles)
            ref = todays[0].open if todays else None
            closes = [c.close for c in data.candles[-2:]]
            if any(c is None for c in closes):
                return None
        elif nivel == "CLOSE":
            ref = data.fundamental.prevClose if data.fundamental else None
            closes = [c.close for c in data.candles[-2:]]
            if any(c is None for c in closes):
                return None
        else:
            periodo = self._param_int(EnumParametro.PERIODO_EMA_CROSSING_ABOVE_BELOW, 9)
            candles_needed = min(len(data.candles), periodo + 1)
            recent = data.candles[-candles_needed:]
            if any(c.close is None for c in recent):
                return None
            closes = [c.close for c in recent]
            ref = _calc_ema(closes, periodo)
        if ref is None or ref <= 0:
            return None
        prev_close, curr_close = closes[-2], closes[-1]
        crossed_up = prev_close <= ref < curr_close
        crossed_down = prev_close >= ref > curr_close
        if not (crossed_up or crossed_down):
            return 0.0
        return ((curr_close / ref) - 1.0) * 100.0


class HaltStrategy(FilterStrategy):
    """Whether trading is halted."""

    def compute_value(self, data: MarketData) -> float:
        if data.snapshot and data.snapshot.tradingHalted:
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


def _calc_atr(candles: list[CandleResponse], period: int, modo: str = "RMA") -> float | None:
    """True Range series suavizada segun el modo elegido -- antes siempre
    aplicaba Wilder's (RMA), ignorando MODO_PROMEDIO_MOVIL_ATR(P). RMA sigue
    siendo el default (el metodo clasico de ATR)."""
    if len(candles) < 2:
        return None
    tr_values = []
    volumes = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i - 1]
        if c.high is None or c.low is None or prev.close is None:
            return None
        tr_values.append(max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close)))
        volumes.append(c.volume or 0)
    if not tr_values:
        return None
    if modo == "EMA":
        return _calc_ema(tr_values, period)
    if modo == "SMA":
        return _calc_sma(tr_values, period)
    if modo == "VMA":
        window_tr = tr_values[-period:] if len(tr_values) > period else tr_values
        window_vol = volumes[-period:] if len(volumes) > period else volumes
        total_vol = sum(window_vol)
        if total_vol <= 0:
            return _calc_sma(tr_values, period)
        return sum(t * v for t, v in zip(window_tr, window_vol)) / total_vol
    # RMA (Wilder's): initial SMA then smoothed (Prior ATR * (N-1) + TR) / N
    if len(tr_values) <= period:
        return sum(tr_values) / len(tr_values)
    atr = sum(tr_values[:period]) / period
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period
    return atr


def _calc_rsi(candles: list[CandleResponse], period: int) -> float | None:
    """Wilder's RSI: seed de las primeras `period` VELAS, luego suavizado --
    antes tomaba `gains[:period]`/`losses[:period]` de las listas ya
    filtradas de ganancias/perdidas de toda la ventana, mezclando barras de
    momentos distintos entre la seed de ganancias y la de perdidas (Wilder
    exige que la seed venga de las mismas primeras `period` velas para
    ambas). Con el margen de barras que timeframe.py siempre pide
    (periodo*3) esta rama se ejecuta en el uso normal, no es un caso raro."""
    if len(candles) < period + 1:
        return None
    if any(c.close is None for c in candles):
        return None
    closes = [c.close for c in candles]
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    if not any(changes):
        return 50.0
    if len(changes) <= period:
        gains = [c for c in changes if c > 0]
        losses = [-c for c in changes if c < 0]
        avg_gain = sum(gains) / len(changes) if gains else 0.0
        avg_loss = sum(losses) / len(changes) if losses else 0.0
    else:
        seed = changes[:period]
        avg_gain = sum(c for c in seed if c > 0) / period
        avg_loss = sum(-c for c in seed if c < 0) / period
        for change in changes[period:]:
            g = change if change > 0 else 0.0
            l = -change if change < 0 else 0.0
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
