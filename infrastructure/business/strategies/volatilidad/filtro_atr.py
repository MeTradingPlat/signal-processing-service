"""Filtro: ATR (Average True Range) - Mide volatilidad promedio."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroATR(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        longitud = self._obtener_valor_int(filtro, "LONGITUD_ATR") or 14
        modo = self._obtener_valor_string(filtro, "MODO_PROMEDIO_MOVIL_ATR") or "EMA"

        if len(candles) < longitud + 1:
            return False

        tr_values = self._calcular_true_range(candles)
        if len(tr_values) < longitud:
            return False

        if modo == "SMA":
            atr_values = self._calcular_sma(tr_values, longitud)
        else:
            atr_values = self._calcular_ema(tr_values, longitud)

        if not atr_values:
            return False

        atr = atr_values[-1]
        resultado = self._evaluar_condicion(atr, min_val, max_val)
        logger.debug(f"ATR: atr={atr:.4f} rango=[{min_val}, {max_val}] -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_ATR")
        return tf if tf else "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        longitud = self._obtener_valor_int(filtro, "LONGITUD_ATR") or 14
        return longitud * 2 + 1
