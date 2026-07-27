from app.strategies.base import FilterStrategy, MarketData


class VolumeSpikeStrategy(FilterStrategy):

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        current = data.candles[-1].volume
        if current is None:
            return None
        previous = [c.volume for c in data.candles[:-1] if c.volume]
        if not previous:
            return None
        max_prev = max(previous)
        if max_prev == 0:
            return None
        return current / max_prev
