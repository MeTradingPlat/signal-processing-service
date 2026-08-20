import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.filtro import Filtro
from app.models.valor import ValorCondicional, ValorFloat, ValorInteger, ValorString
from app.scanner.marketdata_models import CandleResponse, FundamentalResponse, PriceSnapshot
from app.strategies.condition import evaluate_condition

logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    symbol: str
    snapshot: PriceSnapshot | None = None
    candles: list[CandleResponse] | None = None
    fundamental: FundamentalResponse | None = None


class FilterStrategy(ABC):

    def __init__(self, filtro: Filtro | None = None):
        self.filtro = filtro or Filtro()
        self.condition = self._extract_condition()

    @abstractmethod
    def compute_value(self, data: MarketData) -> float | None:
        ...

    def evaluate(self, data: MarketData) -> bool:
        value = self.compute_value(data)
        if value is None:
            logger.debug(
                "%s: %s returned None (missing data), filter not matched",
                data.symbol, type(self).__name__,
            )
            return False
        return evaluate_condition(self.condition, value)

    def _extract_condition(self) -> ValorCondicional | None:
        for p in self.filtro.parametros:
            if isinstance(p.objValorSeleccionado, ValorCondicional):
                return p.objValorSeleccionado
        return None

    def _param_int(self, enum_parametro, default: int) -> int:
        for p in self.filtro.parametros:
            if p.enumParametro == enum_parametro and isinstance(p.objValorSeleccionado, ValorInteger):
                valor = p.objValorSeleccionado.valor
                # "or default" trataba un 0 configurado a proposito (ej.
                # PROPORCION_VOLUMEN_VOLUME_SPIKE=0, "cualquier volumen ya
                # es spike") igual que "nunca se configuro" -- el usuario
                # perdia su valor real en silencio, sin error ni log.
                return valor if valor is not None else default
        return default

    def _param_float(self, enum_parametro, default: float) -> float:
        for p in self.filtro.parametros:
            if p.enumParametro == enum_parametro and isinstance(p.objValorSeleccionado, ValorFloat):
                valor = p.objValorSeleccionado.valor
                return valor if valor is not None else default
        return default

    def _param_str(self, enum_parametro, default: str) -> str:
        for p in self.filtro.parametros:
            if p.enumParametro == enum_parametro and isinstance(p.objValorSeleccionado, ValorString):
                return p.objValorSeleccionado.valor or default
        return default
