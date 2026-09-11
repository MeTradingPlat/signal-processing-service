from app.models.filtro import Filtro
from app.strategies.base import FilterStrategy, MarketData


class _PassthroughStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float:
        return 1.0


def get_strategy(filtro: Filtro) -> FilterStrategy:
    from app.strategies.fundamentales import (
        DaysUntilEarningsStrategy, FloatStrategy, MarketCapStrategy,
        SharesOutstandingStrategy, ShortInterestStrategy, ShortRatioStrategy)
    from app.strategies.momentum import (
        BackToEMAAlertStrategy, DistanceFromEMAStrategy, DistanceFromMAStrategy,
        DistanceFromVWAPStrategy, EMAVWAPSupportResistanceStrategy,
        RSIStrategy, ThroughEMAVWAPAlertStrategy)
    from app.strategies.liquidity_inducement import (
        AccelerationDecelerationStrategy, ConfirmationCandleStrategy,
        LiquidityGrabCandleStrategy, OrderBlockImbalanceStrategy,
        RangeConfluenceStrategy, RangeExtremeProximityStrategy)
    from app.strategies.patrones import (
        BearishBullishEngulfingStrategy, BreakOverRecentHighsLowsStrategy,
        ConsecutiveCandlesStrategy, FirstCandleStrategy, HighLowOfDayStrategy,
        MinutosInMarketStrategy, NewCandleHighLowStrategy,
        OpeningRangeBreakdownStrategy, OpeningRangeBreakoutStrategy,
        PercentagePullbackHighsLowsStrategy, PivotsStrategy)
    from app.strategies.precio_movimiento import (
        ChangeStrategy, CrossingAboveBelowStrategy, GapFromCloseStrategy,
        HaltStrategy, PercentageChangeStrategy, PercentageRangeStrategy,
        PositionInRangeStrategy, PrecioStrategy, RangeDollarsStrategy)
    from app.strategies.volatilidad import ATRPStrategy, ATRStrategy, RelativeRangeStrategy
    from app.strategies.volumen.average_volume import AverageVolumeStrategy
    from app.strategies.volumen.relative_volume import RelativeVolumeStrategy
    from app.strategies.volumen.relative_volume_same_time import RelativeVolumeSameTimeStrategy
    from app.strategies.volumen.volume import VolumeStrategy
    from app.strategies.volumen.volume_spike import VolumeSpikeStrategy
    from app.strategies.volumen.volumen_post_pre import VolumenPostPreStrategy
    mapping = {
        "VOLUME": VolumeStrategy,
        "AVERAGE_VOLUME": AverageVolumeStrategy,
        "VOLUMEN_POST_PRE": VolumenPostPreStrategy,
        "RELATIVE_VOLUME": RelativeVolumeStrategy,
        "RELATIVE_VOLUME_SAME_TIME": RelativeVolumeSameTimeStrategy,
        "VOLUME_SPIKE": VolumeSpikeStrategy,
        "CHANGE": ChangeStrategy,
        "PERCENTAGE_CHANGE": PercentageChangeStrategy,
        "PRECIO": PrecioStrategy,
        "GAP_FROM_CLOSE": GapFromCloseStrategy,
        "POSITION_IN_RANGE": PositionInRangeStrategy,
        "PERCENTAGE_RANGE": PercentageRangeStrategy,
        "RANGE_DOLLARS": RangeDollarsStrategy,
        "CROSSING_ABOVE_BELOW": CrossingAboveBelowStrategy,
        "HALT": HaltStrategy,
        "ATR": ATRStrategy,
        "ATRP": ATRPStrategy,
        "RELATIVE_RANGE": RelativeRangeStrategy,
        "RSI": RSIStrategy,
        "DISTANCE_FROM_VWAP": DistanceFromVWAPStrategy,
        "DISTANCE_FROM_EMA": DistanceFromEMAStrategy,
        "DISTANCE_FROM_MA": DistanceFromMAStrategy,
        "BACK_TO_EMA_ALERT": BackToEMAAlertStrategy,
        "THROUGH_EMA_VWAP_ALERT": ThroughEMAVWAPAlertStrategy,
        "EMA_VWAP_SUPPORT_RESISTANCE": EMAVWAPSupportResistanceStrategy,
        "BEARISH_BULLISH_ENGULFING": BearishBullishEngulfingStrategy,
        "CONSECUTIVE_CANDLES": ConsecutiveCandlesStrategy,
        "FIRST_CANDLE": FirstCandleStrategy,
        "HIGH_LOW_OF_DAY": HighLowOfDayStrategy,
        "NEW_CANDLE_HIGH_LOW": NewCandleHighLowStrategy,
        "PERCENTAGE_PULLBACK_HIGHS_LOWS": PercentagePullbackHighsLowsStrategy,
        "BREAK_OVER_RECENT_HIGHS_LOWS": BreakOverRecentHighsLowsStrategy,
        "OPENING_RANGE_BREAKDOWN": OpeningRangeBreakdownStrategy,
        "OPENING_RANGE_BREAKOUT": OpeningRangeBreakoutStrategy,
        "PIVOTS": PivotsStrategy,
        "MINUTOS_IN_MARKET": MinutosInMarketStrategy,
        "ORDER_BLOCK_IMBALANCE": OrderBlockImbalanceStrategy,
        "LIQUIDITY_GRAB_CANDLE": LiquidityGrabCandleStrategy,
        "ACCELERATION_DECELERATION": AccelerationDecelerationStrategy,
        "CONFIRMATION_CANDLE": ConfirmationCandleStrategy,
        "RANGE_EXTREME_PROXIMITY": RangeExtremeProximityStrategy,
        "RANGE_CONFLUENCE_D1_H4_H1": RangeConfluenceStrategy,
        "FLOAT": FloatStrategy,
        "SHARES_OUTSTANDING": SharesOutstandingStrategy,
        "MARKET_CAP": MarketCapStrategy,
        "SHORT_INTEREST": ShortInterestStrategy,
        "SHORT_RATIO": ShortRatioStrategy,
        "DAYS_UNTIL_EARNINGS": DaysUntilEarningsStrategy,
    }
    name = filtro.enumFiltro.name if filtro.enumFiltro else ""
    cls = mapping.get(name, _PassthroughStrategy)
    return cls(filtro)
