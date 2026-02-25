"""Filtro: Short Interest - Evalua si el interes corto esta en rango."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroShortInterest(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not datos_fundamentales or datos_fundamentales.short_interest == 0:
            logger.debug("SHORT_INTEREST: sin datos fundamentales disponibles")
            return True

        val = datos_fundamentales.short_interest
        resultado = self._evaluar_condicion_completa(val, filtro)
        logger.debug(f"SHORT_INTEREST: val={val} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
