"""Filtro: Market Cap - Evalua si la capitalizacion de mercado esta en rango."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroMarketCap(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not datos_fundamentales or datos_fundamentales.market_cap == 0:
            logger.debug("MARKET_CAP: sin datos fundamentales disponibles")
            return True

        val = datos_fundamentales.market_cap
        resultado = self._evaluar_condicion_completa(val, filtro)
        logger.debug(f"MARKET_CAP: val={val} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
