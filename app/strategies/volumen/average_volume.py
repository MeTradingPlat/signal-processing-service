from app.analysis.indicators import volumes_or_zero
from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData


class AverageVolumeStrategy(FilterStrategy):
    """Promedia el volumen de las ultimas N velas (NUMERO_VELAS_AVERAGE_VOLUME,
    default 20, equivalente intradia al "Average Volume" de 20 sesiones de
    Finviz/TOS) -- ver volumes_or_zero() sobre por que cuenta las de volumen 0
    en vez de descartarlas (confirmado en vivo el 2026-09-08 con CTAS)."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles:
            return None
        n = max(self._param_int(EnumParametro.NUMERO_VELAS_AVERAGE_VOLUME, 20), 1)
        volumes = volumes_or_zero(data.candles[-n:])
        return sum(volumes) / len(volumes)
