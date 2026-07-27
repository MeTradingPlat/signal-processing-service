from app.strategies.base import FilterStrategy, MarketData


class VolumeStrategy(FilterStrategy):

    def compute_value(self, data: MarketData) -> float | None:
        if data.quote and data.quote.volume is not None:
            return data.quote.volume
        if data.candles and data.candles[-1].volume is not None:
            return data.candles[-1].volume
        return None
