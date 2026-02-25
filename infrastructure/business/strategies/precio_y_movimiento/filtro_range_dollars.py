"""Filtro: Range Dollars - Rango en dolares (high - low)."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroRangeDollars(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not candles:
            return False

        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        high = max(c.high for c in candles)
        low = min(c.low for c in candles)
        rango = high - low
        resultado = self._evaluar_condicion_completa(rango, filtro)
        logger.debug(f"RANGE_DOLLARS: rango=${rango:.2f} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_RANGE_DOLLAR")
        return tf if tf else "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 50
