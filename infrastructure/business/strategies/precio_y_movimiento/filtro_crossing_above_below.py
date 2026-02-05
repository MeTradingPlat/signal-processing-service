"""Filtro: Crossing Above/Below - Detecta cruce de precio sobre/bajo un nivel o EMA."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroCrossingAboveBelow(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        min_val, max_val = self._obtener_valor_condicional(filtro)
        nivel_cruce = self._obtener_valor_string(filtro, "NIVEL_CRUCE_CROSSING_ABOVE_BELOW")
        periodo_ema = self._obtener_valor_int(filtro, "PERIODO_EMA_CROSSING_ABOVE_BELOW")

        if periodo_ema > 0:
            closes = [c.close for c in candles]
            ema_values = self._calcular_ema(closes, periodo_ema)
            if len(ema_values) < 2:
                return False

            precio_anterior = candles[-2].close
            precio_actual = candles[-1].close
            ema_anterior = ema_values[-2]
            ema_actual = ema_values[-1]

            cruce_arriba = precio_anterior <= ema_anterior and precio_actual > ema_actual
            cruce_abajo = precio_anterior >= ema_anterior and precio_actual < ema_actual

            resultado = cruce_arriba or cruce_abajo
        elif min_val is not None:
            precio_anterior = candles[-2].close
            precio_actual = candles[-1].close
            nivel = min_val

            cruce_arriba = precio_anterior <= nivel and precio_actual > nivel
            cruce_abajo = precio_anterior >= nivel and precio_actual < nivel

            resultado = cruce_arriba or cruce_abajo
        else:
            return False

        logger.debug(f"CROSSING_ABOVE_BELOW: -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        periodo = self._obtener_valor_int(filtro, "PERIODO_EMA_CROSSING_ABOVE_BELOW")
        return max(periodo + 2, 50)
