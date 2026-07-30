from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData
from app.strategies.precio_movimiento import _calc_ema, _calc_rsi, _calc_sma, _calc_vwap


class RSIStrategy(FilterStrategy):
    """Relative Strength Index."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles:
            return None
        period = self._param_int(EnumParametro.PERIODO_RSI, 14)
        return _calc_rsi(data.candles, period)


class DistanceFromVWAPStrategy(FilterStrategy):
    """Distance from VWAP in %."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or data.candles[-1].close is None:
            return None
        vwap = _calc_vwap(data.candles)
        if vwap is None or vwap <= 0:
            return None
        price = data.candles[-1].close
        return ((price / vwap) - 1.0) * 100.0


class DistanceFromEMAStrategy(FilterStrategy):
    """Distance from EMA in %."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or any(c.close is None for c in data.candles):
            return None
        periodo = self._param_int(EnumParametro.PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA, 9)
        closes = [c.close for c in data.candles]
        ema = _calc_ema(closes, periodo)
        if ema <= 0:
            return None
        return ((closes[-1] / ema) - 1.0) * 100.0


class DistanceFromMAStrategy(FilterStrategy):
    """Distance from SMA in %."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or any(c.close is None for c in data.candles):
            return None
        periodo = self._param_int(EnumParametro.PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA, 20)
        closes = [c.close for c in data.candles]
        sma = _calc_sma(closes, periodo)
        if sma <= 0:
            return None
        return ((closes[-1] / sma) - 1.0) * 100.0


class BackToEMAAlertStrategy(FilterStrategy):
    """Price pulling back to EMA."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 3 or any(c.close is None for c in data.candles):
            return None
        periodo = self._param_int(EnumParametro.PERIODO_EMA_BACK_TO_EMA, 9)
        closes = [c.close for c in data.candles]
        ema = _calc_ema(closes, periodo)
        if ema <= 0:
            return None
        return ((closes[-1] / ema) - 1.0) * 100.0


class ThroughEMAVWAPAlertStrategy(FilterStrategy):
    """Price actually crossing through EMA/VWAP this bar -- el cierre previo
    estaba a un lado de la linea y el actual quedo del otro. Antes solo
    calculaba la distancia actual (identica a DistanceFromEMA), sin comparar
    contra la vela anterior, asi que nunca detectaba un cruce real, solo
    "que tan cerca esta ahora". Devuelve 0.0 cuando no hubo cruce en esta
    vela (mismo patron 0/valor-con-signo que las demas estrategias de
    patrones), o la distancia % con signo (positivo = cruzo hacia arriba)
    cuando si lo hubo."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2 or any(c.close is None for c in data.candles):
            return None
        linea = self._param_str(EnumParametro.THROUGH_EMA_VWAP_LINEA_CRUCE, "EMA")
        periodo = self._param_int(EnumParametro.THROUGH_EMA_VWAP_PERIODO_EMA, 9)
        closes = [c.close for c in data.candles]
        if linea == "VWAP":
            ref = _calc_vwap(data.candles)
        else:
            ref = _calc_ema(closes, periodo)
        if ref is None or ref <= 0:
            return None
        prev_close, curr_close = closes[-2], closes[-1]
        crossed_up = prev_close <= ref < curr_close
        crossed_down = prev_close >= ref > curr_close
        if not (crossed_up or crossed_down):
            return 0.0
        return ((curr_close / ref) - 1.0) * 100.0


class EMAVWAPSupportResistanceStrategy(FilterStrategy):
    """Price bouncing off EMA/VWAP support/resistance."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 3 or any(c.close is None for c in data.candles):
            return None
        linea = self._param_str(EnumParametro.LINEA_REFERENCIA_EMA_VWAP_SUPPORT, "EMA")
        periodo = self._param_int(EnumParametro.PERIODO_EMA_EMA_VWAP_SUPPORT, 9)
        closes = [c.close for c in data.candles]
        if linea == "VWAP":
            ref = _calc_vwap(data.candles)
        else:
            ref = _calc_ema(closes, periodo)
        if ref is None or ref <= 0:
            return None
        prev_distance = (closes[-2] / ref) - 1.0
        curr_distance = (closes[-1] / ref) - 1.0
        return abs(curr_distance) - abs(prev_distance)
