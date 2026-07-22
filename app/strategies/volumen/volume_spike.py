from app.strategies.base import FilterStrategy, MarketData


class VolumeSpikeStrategy(FilterStrategy):

    def compute_value(self, data: MarketData) -> float:
        if not data.candles or len(data.candles) < 2:
            return 0.0
        current = data.candles[-1].volume or 0.0
        previous = [c.volume for c in data.candles[:-1] if c.volume]
        if not previous:
            return 0.0
        max_prev = max(previous)
        if max_prev == 0:
            return 0.0
        return current / max_prev
