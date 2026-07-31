from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData


class VolumeSpikeStrategy(FilterStrategy):
    """Volumen actual >= proporcion configurada x promedio de las N velas
    previas (definicion estandar de la industria) -- antes usaba TODAS las
    velas fetcheadas (ignorando NUMERO_VELAS_VOLUME_SPIKE) y comparaba
    contra el MAXIMO en vez del promedio (ignorando
    PROPORCION_VOLUMEN_VOLUME_SPIKE), asi que ambos parametros que el
    usuario configura en el formulario nunca se usaban."""

    def compute_value(self, data: MarketData) -> float | None:
        n = self._param_int(EnumParametro.NUMERO_VELAS_VOLUME_SPIKE, 5)
        proporcion = self._param_float(EnumParametro.PROPORCION_VOLUMEN_VOLUME_SPIKE, 1.5)
        if not data.candles or len(data.candles) < n + 1:
            return None
        current = data.candles[-1].volume
        previous = [c.volume for c in data.candles[-(n + 1):-1] if c.volume is not None]
        if current is None or len(previous) < n:
            return None
        avg_prev = sum(previous) / len(previous)
        if avg_prev == 0:
            return None
        return 1.0 if (current / avg_prev) >= proporcion else 0.0
