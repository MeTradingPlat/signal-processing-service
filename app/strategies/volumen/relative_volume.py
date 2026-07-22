from app.strategies.base import FilterStrategy, MarketData


class RelativeVolumeStrategy(FilterStrategy):

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        current = data.candles[-1].volume or 0.0
        previous = [c.volume for c in data.candles[:-1] if c.volume]
        if not previous or sum(previous) == 0:
            return 0.0
        avg = sum(previous) / len(previous)
        return (current / avg) * 100.0
