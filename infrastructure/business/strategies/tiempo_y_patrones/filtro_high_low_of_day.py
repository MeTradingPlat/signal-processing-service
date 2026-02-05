"""Filtro: High/Low Of Day - Detecta nuevo high o low del dia."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroHighLowOfDay(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        opcion = self._obtener_valor_string(filtro, "OPCION_EXTREMO_HIGH_LOW_DAY") or "HIGH"

        ultima = candles[-1]
        anteriores = candles[:-1]

        if opcion == "HIGH":
            max_anterior = max(c.high for c in anteriores)
            resultado = ultima.high >= max_anterior
        else:
            min_anterior = min(c.low for c in anteriores)
            resultado = ultima.low <= min_anterior

        logger.debug(f"HIGH_LOW_OF_DAY ({opcion}): -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_HIGH_LOW_DAY")
        return tf if tf else "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 78  # ~1 dia de M5
