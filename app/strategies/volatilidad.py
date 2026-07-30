from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData
from app.strategies.precio_movimiento import _calc_atr


class ATRStrategy(FilterStrategy):
    """Average True Range over N candles."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles:
            return None
        period = self._param_int(EnumParametro.LONGITUD_ATR, 14)
        modo = self._param_str(EnumParametro.MODO_PROMEDIO_MOVIL_ATR, "RMA")
        return _calc_atr(data.candles, period, modo)


class ATRPStrategy(FilterStrategy):
    """ATR as percentage of price."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles:
            return None
        period = self._param_int(EnumParametro.PERIODO_ATR_ATRP, 14)
        modo = self._param_str(EnumParametro.TIPO_PROMEDIO_MOVIL_ATRP, "RMA")
        atr = _calc_atr(data.candles, period, modo)
        price = data.candles[-1].close
        if atr is None or price is None or price <= 0:
            return None
        return (atr / price) * 100.0


class RelativeRangeStrategy(FilterStrategy):
    """Current candle range relative to ATR."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        current = data.candles[-1]
        if current.high is None or current.low is None:
            return None
        c_range = current.high - current.low
        atr = _calc_atr(data.candles, 14)
        if atr is None or atr <= 0:
            return None
        return (c_range / atr) * 100.0
