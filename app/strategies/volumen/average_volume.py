from app.strategies.base import FilterStrategy, MarketData


class AverageVolumeStrategy(FilterStrategy):

    def compute_value(self, data: MarketData) -> float:
        if not data.candles:
            return 0.0
        volumes = [c.volume for c in data.candles if c.volume]
        if not volumes:
            return 0.0
        return sum(volumes) / len(volumes)
