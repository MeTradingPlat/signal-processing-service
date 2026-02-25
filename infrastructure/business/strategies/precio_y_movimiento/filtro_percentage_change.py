"""Filtro: Percentage Change - Cambio porcentual en un timeframe."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroPercentageChange(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        precio_inicial = candles[0].close
        precio_actual = candles[-1].close

        if precio_inicial == 0:
            return False

        pct_change = ((precio_actual - precio_inicial) / precio_inicial) * 100
        resultado = self._evaluar_condicion_completa(pct_change, filtro)
        logger.debug(f"PERCENTAGE_CHANGE: pct={pct_change:.2f}% -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_PERCENTAGE_CHANGE_PERCENT")
        return tf if tf else "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 50
