from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData
from app.strategies.precio_movimiento import _calc_atr


class ATRStrategy(FilterStrategy):
    """Average True Range over N candles."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles:
            return 0.0
        period = self._param_int(EnumParametro.LONGITUD_ATR, 14)
        return _calc_atr(data.candles, period)


class ATRPStrategy(FilterStrategy):
    """ATR as percentage of price."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles:
            return 0.0
        period = self._param_int(EnumParametro.PERIODO_ATR_ATRP, 14)
        atr = _calc_atr(data.candles, period)
        price = (data.candles[-1].close or 0.0) if data.candles else 0.0
        if price <= 0:
            return 0.0
        return (atr / price) * 100.0


class RelativeRangeStrategy(FilterStrategy):
    """Current candle range relative to ATR."""

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        current = data.candles[-1]
        c_range = (current.high or 0.0) - (current.low or 0.0)
        atr = _calc_atr(data.candles, 14)
        if atr <= 0:
            return 0.0
        return (c_range / atr) * 100.0
