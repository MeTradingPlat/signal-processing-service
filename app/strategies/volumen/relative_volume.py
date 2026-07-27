from app.strategies.base import FilterStrategy, MarketData


class RelativeVolumeStrategy(FilterStrategy):

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        current = data.candles[-1].volume
        if current is None:
            return None
        previous = [c.volume for c in data.candles[:-1] if c.volume]
        if not previous or sum(previous) == 0:
            return None
        avg = sum(previous) / len(previous)
        return (current / avg) * 100.0
