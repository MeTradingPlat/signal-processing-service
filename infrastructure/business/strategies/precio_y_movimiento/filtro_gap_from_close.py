"""Filtro: Gap From Close - Evalua el gap entre el cierre anterior y apertura actual."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroGapFromClose(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        formato = self._obtener_valor_string(filtro, "FORMATO_GAP_FROM_CLOSE")

        cierre_anterior = candles[-2].close
        apertura_actual = candles[-1].open

        if cierre_anterior == 0:
            return False

        if formato == "PORCENTAJE":
            gap = ((apertura_actual - cierre_anterior) / cierre_anterior) * 100
        else:
            gap = apertura_actual - cierre_anterior

        resultado = self._evaluar_condicion(gap, min_val, max_val)
        logger.debug(f"GAP_FROM_CLOSE: gap={gap:.4f} rango=[{min_val}, {max_val}] -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 2
