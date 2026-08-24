from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData


class VolumenPostPreStrategy(FilterStrategy):
    """TIPO_VOLUMEN elige sobre que volumen se aplica la condicion (antes se
    ignoraba y siempre sumaba pre+post): PRE = solo pre-market, POST = solo
    post-market, AMBOS = la suma (default historico). Los escaneres creados
    antes de existir la opcion no traen el parametro y caen en AMBOS."""

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
        if pre is None or post is None:
            return None
        return float(pre + post)
