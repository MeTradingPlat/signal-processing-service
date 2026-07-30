from app.models.enums import EnumParametro
from app.strategies.base import FilterStrategy, MarketData


class VolumeStrategy(FilterStrategy):
    """TIPO_VOLUMEN elige la medida (antes se ignoraba y siempre devolvia el
    volumen del dia): CIERRE = volumen acumulado de la sesion regular (lo que
    ya habia), APERTURA = volumen de pre-market."""

    def compute_value(self, data: MarketData) -> float | None:
        tipo = self._param_str(EnumParametro.TIPO_VOLUMEN, "CIERRE")
        if tipo == "APERTURA":
            if data.fundamental and data.fundamental.preMarketVolume is not None:
                return data.fundamental.preMarketVolume
            return None
        if data.quote and data.quote.volume is not None:
            return data.quote.volume
        if data.candles and data.candles[-1].volume is not None:
            return data.candles[-1].volume
        return None
