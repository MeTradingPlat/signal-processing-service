from app.strategies.base import FilterStrategy, MarketData


class FloatStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float | None:
        if data.fundamental is None or data.fundamental.floatShares is None:
            return None
        return float(data.fundamental.floatShares)


class SharesOutstandingStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float | None:
        if data.fundamental is None or data.fundamental.sharesOutstanding is None:
            return None
        return float(data.fundamental.sharesOutstanding)


class MarketCapStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float | None:
        if data.fundamental is None or data.fundamental.marketCap is None:
            return None
        return float(data.fundamental.marketCap)


class ShortInterestStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float | None:
        if data.fundamental is None or data.fundamental.shortInterest is None:
            return None
        return float(data.fundamental.shortInterest)


class ShortRatioStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float | None:
        if data.fundamental is None or data.fundamental.shortRatio is None:
            return None
        return float(data.fundamental.shortRatio)


class DaysUntilEarningsStrategy(FilterStrategy):
    def compute_value(self, data: MarketData) -> float | None:
        if data.fundamental is None or data.fundamental.daysUntilEarnings is None:
            return None
        return float(data.fundamental.daysUntilEarnings)
