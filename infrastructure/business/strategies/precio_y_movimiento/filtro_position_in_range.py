"""Filtro: Position In Range - Posicion del precio dentro del rango high-low."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroPositionInRange(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not candles:
            return False

        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        high = max(c.high for c in candles)
        low = min(c.low for c in candles)
        precio_actual = candles[-1].close

        rango = high - low
        if rango == 0:
            return False

        posicion = ((precio_actual - low) / rango) * 100
        resultado = self._evaluar_condicion_completa(posicion, filtro)
        logger.debug(f"POSITION_IN_RANGE: pos={posicion:.1f}% -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_POSITION_IN_RANGE")
        return tf if tf else "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 50
