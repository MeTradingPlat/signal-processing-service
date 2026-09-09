from app.analysis.indicators import volumes_or_zero
from app.strategies.base import FilterStrategy, MarketData


class AverageVolumeStrategy(FilterStrategy):
    """Promedia el volumen de TODAS las velas del rango -- ver
    volumes_or_zero() sobre por que cuenta las de volumen 0 en vez de
    descartarlas (confirmado en vivo el 2026-09-08 con CTAS)."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles:
            return None
        volumes = volumes_or_zero(data.candles)
        return sum(volumes) / len(volumes)
