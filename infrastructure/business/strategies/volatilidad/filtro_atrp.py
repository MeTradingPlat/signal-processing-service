"""Filtro: ATRP (ATR Percentage) - ATR como porcentaje del precio."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroATRP(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        periodo = self._obtener_valor_int(filtro, "PERIODO_ATR_ATRP") or 14
        modo = self._obtener_valor_string(filtro, "TIPO_PROMEDIO_MOVIL_ATRP") or "EMA"

        if len(candles) < periodo + 1:
            return False

        tr_values = self._calcular_true_range(candles)
        if len(tr_values) < periodo:
            return False

        if modo == "SMA":
            atr_values = self._calcular_sma(tr_values, periodo)
        else:
            atr_values = self._calcular_ema(tr_values, periodo)

        if not atr_values:
            return False

        atr = atr_values[-1]
        precio = candles[-1].close
        if precio == 0:
            return False

        atrp = (atr / precio) * 100

        resultado = self._evaluar_condicion(atrp, min_val, max_val)
        logger.debug(f"ATRP: atrp={atrp:.2f}% rango=[{min_val}, {max_val}] -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_ATRP")
        return tf if tf else "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        periodo = self._obtener_valor_int(filtro, "PERIODO_ATR_ATRP") or 14
        return periodo * 2 + 1
