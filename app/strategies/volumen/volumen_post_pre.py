from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData


class VolumenPostPreStrategy(FilterStrategy):
    """TIPO_VOLUMEN elige sobre que volumen se aplica la condicion (antes se
    ignoraba y siempre sumaba pre+post): PRE = solo pre-market, POST = solo
    post-market, AMBOS = la suma (default historico). Los escaneres creados
    antes de existir la opcion no traen el parametro y caen en AMBOS.

    AMBOS usa postMarketVolume si ya hay alguno (>0) y si no cae a
    prevPostMarketVolume (el de AYER) -- un escaner que corre en premarket
    (ej. 04:00-09:30 ET) nunca ve el postMarketVolume de HOY, esa sesion
    todavia no paso: es 0 genuina y estructuralmente, no ausencia de dato
    (ver domain.Fundamentals.PrevPostMarketVolume en marketdata-service).
    Sin este fallback, AMBOS en esa ventana horaria era identico a filtrar
    solo por PRE sin que nadie lo supiera -- confirmado en vivo el
    2026-09-03 con el escaner 'volumen test'."""

    def compute_value(self, data: MarketData) -> float | None:
        if not data.fundamental:
            return None
        pre = data.fundamental.preMarketVolume
        post = data.fundamental.postMarketVolume

        tipo = self._param_str(EnumParametro.TIPO_VOLUMEN, "AMBOS")
        if tipo == "PRE":
            return float(pre) if pre is not None else None
        if tipo == "POST":
            return float(post) if post is not None else None
        if pre is None:
            return None
        effective_post = post if post else data.fundamental.prevPostMarketVolume
        if effective_post is None:
            return None
        return float(pre + effective_post)
