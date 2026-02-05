"""Filtro: Relative Range - Rango actual relativo al rango promedio historico."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroRelativeRange(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        rango_actual = candles[-1].high - candles[-1].low
        rangos_hist = [c.high - c.low for c in candles[:-1]]
        avg_rango = sum(rangos_hist) / len(rangos_hist) if rangos_hist else 1

        if avg_rango == 0:
            return False

        relative_range = (rango_actual / avg_rango) * 100

        resultado = self._evaluar_condicion(relative_range, min_val, max_val)
        logger.debug(f"RELATIVE_RANGE: rr={relative_range:.1f}% rango=[{min_val}, {max_val}] -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 21
