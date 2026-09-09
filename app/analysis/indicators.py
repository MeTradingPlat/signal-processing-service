from datetime import datetime, timezone

from app.scanner.marketdata_models import CandleResponse


def calculate_ema(values: list[float], period: int) -> float:
    if len(values) < period:
        period = len(values)
    if period == 0:
        return 0.0
    multiplier = 2.0 / (period + 1.0)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v - ema) * multiplier + ema
    return ema


def calculate_sma(values: list[float], period: int) -> float:
    if len(values) < period:
        period = len(values)
    return sum(values[-period:]) / period if period > 0 else 0.0


def calculate_atr(candles: list[CandleResponse], period: int, modo: str = "RMA") -> float | None:
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
        return calculate_ema(tr_values, period)
    if modo == "SMA":
        return calculate_sma(tr_values, period)
    if modo == "VMA":
        window_tr = tr_values[-period:] if len(tr_values) > period else tr_values
        window_vol = volumes[-period:] if len(volumes) > period else volumes
        total_vol = sum(window_vol)
        if total_vol <= 0:
            return calculate_sma(tr_values, period)
        return sum(t * v for t, v in zip(window_tr, window_vol)) / total_vol
    # RMA (Wilder's): initial SMA then smoothed (Prior ATR * (N-1) + TR) / N
    if len(tr_values) <= period:
        return sum(tr_values) / len(tr_values)
    atr = sum(tr_values[:period]) / period
    for i in range(period, len(tr_values)):
        atr = (atr * (period - 1) + tr_values[i]) / period
    return atr


def calculate_rsi(candles: list[CandleResponse], period: int) -> float | None:
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


def calculate_vwap(candles: list[CandleResponse]) -> float | None:
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

    today = datetime.now(timezone.utc).date()
    todays = [c for c in candles if c.timestamp and c.timestamp.date() == today]

    tv, tp = _accumulate(todays)
    if tp <= 0:
        fallback = todays if todays else candles[-max(1, len(candles) // 10):]
        tv, tp = _accumulate(fallback)
    return tv / tp if tp > 0 else None


def todays_candles(candles: list[CandleResponse] | None) -> list[CandleResponse]:
    """Isola las velas de la sesion de hoy -- varias estrategias de patrones
    usaban candles[0]/candles[-1] asumiendo que la ventana pedida arrancaba
    en la apertura del dia, pero es solo "las ultimas N barras", que puede
    arrancar en cualquier punto (incluso un dia anterior)."""
    if not candles:
        return []
    today = datetime.now(timezone.utc).date()
    return [c for c in candles if c.timestamp and c.timestamp.date() == today]


def volumes_or_zero(candles: list[CandleResponse]) -> list[float]:
    """Volumen de cada vela contando None/0 como 0 en vez de descartar la
    vela -- descartarla infla el promedio de un simbolo poco liquido
    (confirmado en vivo el 2026-09-08 con CTAS, ver AverageVolumeStrategy/
    RelativeVolumeStrategy)."""
    return [c.volume or 0 for c in candles]
