from app.strategies.base import FilterStrategy, MarketData


class AverageVolumeStrategy(FilterStrategy):
    """Promedia el volumen de TODAS las velas del rango, contando las de
    volumen 0 como 0 en vez de descartarlas -- descartarlas (como hacia
    antes, `if c.volume`) infla artificialmente el promedio de un simbolo
    poco liquido: un rango con una sola vela real de 100 acciones y el
    resto en cero daba promedio=100 (la unica que sobrevivia el filtro) en
    vez del promedio real, mucho mas bajo, que refleja que casi no opera.
    Confirmado en vivo el 2026-09-08: dejaba pasar un falso positivo de
    'SPIKES 5 MIN' en CTAS pese al filtro AVERAGE_VOLUME > 15000 que
    deberia haberlo bloqueado."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.candles:
            return None
        volumes = [c.volume or 0 for c in data.candles]
        return sum(volumes) / len(volumes)
