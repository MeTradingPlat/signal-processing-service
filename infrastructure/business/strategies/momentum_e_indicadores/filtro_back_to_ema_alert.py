"""Filtro: Back To EMA Alert - Detecta cuando el precio regresa a la EMA."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroBackToEmaAlert(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        periodo = self._obtener_valor_int(filtro, "PERIODO_EMA_BACK_TO_EMA")
        if periodo <= 0:
            periodo = 20

        closes = [c.close for c in candles]
        if len(closes) < periodo + 2:
            return False

        ema_values = self._calcular_ema(closes, periodo)
        if len(ema_values) < 2:
            return False

        precio_anterior = candles[-2].close
        precio_actual = candles[-1].close
        ema_anterior = ema_values[-2]
        ema_actual = ema_values[-1]

        # Detecta toque/regreso a EMA (estaba lejos y ahora toca)
        dist_anterior = abs(precio_anterior - ema_anterior) / ema_anterior * 100
        dist_actual = abs(precio_actual - ema_actual) / ema_actual * 100

        # Si la distancia se redujo significativamente y ahora esta cerca (<0.5%)
        resultado = dist_anterior > 1.0 and dist_actual < 0.5
        logger.debug(f"BACK_TO_EMA: dist_ant={dist_anterior:.2f}% dist_act={dist_actual:.2f}% -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_BACK_TO_EMA")
        return tf if tf else "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        periodo = self._obtener_valor_int(filtro, "PERIODO_EMA_BACK_TO_EMA") or 20
        return periodo * 2
