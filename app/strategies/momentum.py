from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData
from app.strategies.precio_movimiento import _calc_ema, _calc_rsi, _calc_sma, _calc_vwap


def _effective_vwap(data: MarketData) -> float:
    """Prefer the live tick-accumulated VWAP; fall back to candle-based estimate."""
    if data.quote and data.quote.vwap:
        return data.quote.vwap
    if data.candles:
        return _calc_vwap(data.candles)
    return 0.0


class RSIStrategy(FilterStrategy):
    """Relative Strength Index."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles:
            return 50.0
        period = self._param_int(EnumParametro.PERIODO_RSI, 14)
        return _calc_rsi(data.candles, period)


class DistanceFromVWAPStrategy(FilterStrategy):
    """Distance from VWAP in %."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles:
            return 0.0
        vwap = _effective_vwap(data)
        if vwap <= 0:
            return 0.0
        price = data.candles[-1].close or 0.0
        return ((price / vwap) - 1.0) * 100.0


class DistanceFromEMAStrategy(FilterStrategy):
    """Distance from EMA in %."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles:
            return 0.0
        periodo = self._param_int(EnumParametro.PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA, 9)
        closes = [c.close or 0.0 for c in data.candles]
        ema = _calc_ema(closes, periodo)
        if ema <= 0:
            return 0.0
        return ((closes[-1] / ema) - 1.0) * 100.0


class DistanceFromMAStrategy(FilterStrategy):
    """Distance from SMA in %."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles:
            return 0.0
        periodo = self._param_int(EnumParametro.PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA, 20)
        closes = [c.close or 0.0 for c in data.candles]
        sma = _calc_sma(closes, periodo)
        if sma <= 0:
            return 0.0
        return ((closes[-1] / sma) - 1.0) * 100.0


class BackToEMAAlertStrategy(FilterStrategy):
    """Price pulling back to EMA."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 3:
            return 0.0
        periodo = self._param_int(EnumParametro.PERIODO_EMA_BACK_TO_EMA, 9)
        closes = [c.close or 0.0 for c in data.candles]
        ema = _calc_ema(closes, periodo)
        if ema <= 0:
            return 0.0
        return ((closes[-1] / ema) - 1.0) * 100.0


class ThroughEMAVWAPAlertStrategy(FilterStrategy):
    """Price crossing through EMA/VWAP."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        linea = self._param_str(EnumParametro.THROUGH_EMA_VWAP_LINEA_CRUCE, "EMA")
        periodo = self._param_int(EnumParametro.THROUGH_EMA_VWAP_PERIODO_EMA, 9)
        closes = [c.close or 0.0 for c in data.candles]
        if linea == "VWAP":
            ref = _effective_vwap(data)
        else:
            ref = _calc_ema(closes, periodo)
        if ref <= 0:
            return 0.0
        return ((closes[-1] / ref) - 1.0) * 100.0


class EMAVWAPSupportResistanceStrategy(FilterStrategy):
    """Price bouncing off EMA/VWAP support/resistance."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 3:
            return 0.0
        linea = self._param_str(EnumParametro.LINEA_REFERENCIA_EMA_VWAP_SUPPORT, "EMA")
        periodo = self._param_int(EnumParametro.PERIODO_EMA_EMA_VWAP_SUPPORT, 9)
        closes = [c.close or 0.0 for c in data.candles]
        if linea == "VWAP":
            ref = _effective_vwap(data)
        else:
            ref = _calc_ema(closes, periodo)
        if ref <= 0:
            return 0.0
        prev_distance = (closes[-2] / ref) - 1.0
        curr_distance = (closes[-1] / ref) - 1.0
        return abs(curr_distance) - abs(prev_distance)
