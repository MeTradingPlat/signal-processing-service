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

        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return True

        resultado = self._evaluar_condicion(float(datos_fundamentales.days_until_earnings), min_val, max_val)
        logger.debug(f"DAYS_UNTIL_EARNINGS: val={datos_fundamentales.days_until_earnings} rango=[{min_val}, {max_val}] -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
