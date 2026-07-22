from app.strategies.base import FilterStrategy, MarketData


class VolumenPostPreStrategy(FilterStrategy):

    def compute_value(self, data: MarketData) -> float:
        if not data.fundamental:
            return 0.0
        pre = data.fundamental.preMarketVolume or 0
        post = data.fundamental.postMarketVolume or 0
        return float(pre + post)
