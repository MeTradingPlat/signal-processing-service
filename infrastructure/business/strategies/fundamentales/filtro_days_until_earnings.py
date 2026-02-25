"""Filtro: Days Until Earnings - Evalua si los dias hasta earnings estan en rango."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroDaysUntilEarnings(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not datos_fundamentales or datos_fundamentales.days_until_earnings == 0:
            logger.debug("DAYS_UNTIL_EARNINGS: sin datos fundamentales disponibles")
            return True

        val = float(datos_fundamentales.days_until_earnings)
        resultado = self._evaluar_condicion_completa(val, filtro)
        logger.debug(f"DAYS_UNTIL_EARNINGS: val={val} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
