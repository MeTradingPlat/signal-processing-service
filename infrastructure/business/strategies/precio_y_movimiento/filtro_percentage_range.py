"""Filtro: Percentage Range - Rango porcentual (high-low)/low."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroPercentageRange(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not candles:
            return False

        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        high = max(c.high for c in candles)
        low = min(c.low for c in candles)

        if low == 0:
            return False

        pct_range = ((high - low) / low) * 100
        resultado = self._evaluar_condicion_completa(pct_range, filtro)
        logger.debug(f"PERCENTAGE_RANGE: pct={pct_range:.2f}% -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_PERCENTAGE_RANGE_PERCENT")
        return tf if tf else "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 50
