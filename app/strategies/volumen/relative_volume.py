from app.analysis.indicators import volumes_or_zero
from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData


class RelativeVolumeStrategy(FilterStrategy):
    """Volumen actual vs. promedio de las ultimas N velas previas
    (NUMERO_VELAS_RELATIVE_VOLUME, default 20) -- ver volumes_or_zero() sobre
    por que cuenta las de volumen 0 en vez de descartarlas (mismo bug ya
    corregido en AverageVolumeStrategy, confirmado en vivo el 2026-09-08 con
    CTAS), lo que aca hace lo opuesto: subestima el volumen relativo en vez
    de sobreestimarlo, dejando pasar por debajo del radar un spike real en un
    simbolo con huecos de trading."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles or len(data.candles) < 2:
            return None
        current = data.candles[-1].volume
        if current is None:
            return None
        n = max(self._param_int(EnumParametro.NUMERO_VELAS_RELATIVE_VOLUME, 20), 1)
        previous = volumes_or_zero(data.candles[-(n + 1):-1])
        if sum(previous) == 0:
            return None
        avg = sum(previous) / len(previous)
        return (current / avg) * 100.0
