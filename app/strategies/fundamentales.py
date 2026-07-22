from app.strategies.base import FilterStrategy, MarketData


class FloatStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float:
        if data.fundamental is None:
            return 0.0
        return float(data.fundamental.floatShares or 0)


class SharesOutstandingStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float:
        if data.fundamental is None:
            return 0.0
        return float(data.fundamental.sharesOutstanding or 0)


class MarketCapStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float:
        if data.fundamental is None:
            return 0.0
        return float(data.fundamental.marketCap or 0)


class ShortInterestStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float:
        if data.fundamental is None:
            return 0.0
        return float(data.fundamental.shortInterest or 0)


class ShortRatioStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float:
        if data.fundamental is None:
            return 0.0
        return float(data.fundamental.shortRatio or 0)


class DaysUntilEarningsStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float:
        if data.fundamental is None:
            return 0.0
        return float(data.fundamental.daysUntilEarnings or 0)
