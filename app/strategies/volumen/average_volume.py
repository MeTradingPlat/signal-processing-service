from app.strategies.base import FilterStrategy, MarketData


class AverageVolumeStrategy(FilterStrategy):

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles:
            return None
        volumes = [c.volume for c in data.candles if c.volume]
        if not volumes:
            return None
        return sum(volumes) / len(volumes)
