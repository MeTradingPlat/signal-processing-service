"""Filtro: Opening Range Breakdown - Rompimiento bajista del rango de apertura."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroOpeningRangeBreakdown(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        # El rango de apertura se define con la primera vela
        primera = candles[0]
        ultima = candles[-1]

        resultado = ultima.close < primera.low
        logger.debug(f"OPENING_RANGE_BREAKDOWN: low_apertura={primera.low:.2f} close={ultima.close:.2f} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_OPENING_RANGE_BREAKDOWN")
        return tf if tf else "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 78
