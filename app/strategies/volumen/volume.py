from app.strategies.base import FilterStrategy, MarketData


class VolumeStrategy(FilterStrategy):

    def compute_value(self, data: MarketData) -> float:
        if data.quote and data.quote.volume:
            return data.quote.volume
        if data.candles:
            return data.candles[-1].volume or 0.0
        return 0.0
