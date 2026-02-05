"""Filtro: Short Ratio - Evalua si el ratio corto esta en rango."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroShortRatio(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not datos_fundamentales or datos_fundamentales.short_ratio == 0:
            logger.debug("SHORT_RATIO: sin datos fundamentales disponibles")
            return True

        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return True

        resultado = self._evaluar_condicion(datos_fundamentales.short_ratio, min_val, max_val)
        logger.debug(f"SHORT_RATIO: val={datos_fundamentales.short_ratio} rango=[{min_val}, {max_val}] -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
