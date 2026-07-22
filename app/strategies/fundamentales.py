from app.strategies.base import FilterStrategy, MarketData


class FloatStrategy(FilterStrategy):
    """Float shares."""

    def compute_value(self, data: MarketData) -> float:
        f = data.fundamental
        return float(f.floatShares or 0)


class SharesOutstandingStrategy(FilterStrategy):
    """Shares outstanding."""

    def compute_value(self, data: MarketData) -> float:
        f = data.fundamental
        return float(f.sharesOutstanding or 0)


class MarketCapStrategy(FilterStrategy):
    """Market capitalization."""

    def compute_value(self, data: MarketData) -> float:
        f = data.fundamental
        return float(f.marketCap or 0)


class ShortInterestStrategy(FilterStrategy):
    """Short interest as % of float."""

    def compute_value(self, data: MarketData) -> float:
        f = data.fundamental
        return float(f.shortInterest or 0)


class ShortRatioStrategy(FilterStrategy):
    """Days to cover (short ratio)."""

    def compute_value(self, data: MarketData) -> float:
        f = data.fundamental
        return float(f.shortRatio or 0)


class DaysUntilEarningsStrategy(FilterStrategy):
    """Days until next earnings report."""

    def compute_value(self, data: MarketData) -> float:
        f = data.fundamental
        return float(f.daysUntilEarnings or 0)
