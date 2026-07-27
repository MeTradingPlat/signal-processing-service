from app.strategies.base import FilterStrategy, MarketData


class VolumenPostPreStrategy(FilterStrategy):

    def compute_value(self, data: MarketData) -> float | None:
        if not data.fundamental:
            return None
        pre = data.fundamental.preMarketVolume
        post = data.fundamental.postMarketVolume
        if pre is None or post is None:
            return None
        return float(pre + post)
