"""Filtro: Float - Evalua si el float de acciones esta en el rango condicional."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroFloat(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not datos_fundamentales or datos_fundamentales.float_shares == 0:
            logger.debug("FLOAT: sin datos fundamentales disponibles")
            return True

        val = datos_fundamentales.float_shares
        resultado = self._evaluar_condicion_completa(val, filtro)
        logger.debug(f"FLOAT: float={val} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
