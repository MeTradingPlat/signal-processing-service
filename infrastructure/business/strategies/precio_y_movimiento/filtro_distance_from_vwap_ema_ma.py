"""Filtro: Distance From VWAP/EMA/MA - Distancia del precio a una linea de referencia."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroDistanceFromVwapEmaMa(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not candles:
            return False

        linea_ref = self._obtener_valor_string(filtro, "LINEA_REFERENCIA_DISTANCE_FROM_VWAP_EMA_MA") or "VWAP"
        modo = self._obtener_valor_string(filtro, "MODO_DISTANCIA_DISTANCE_FROM_VWAP_EMA_MA") or "PORCENTAJE"
        periodo = self._obtener_valor_int(filtro, "PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA")

        precio_actual = candles[-1].close
        closes = [c.close for c in candles]

        if linea_ref == "VWAP":
            valor_linea = self._calcular_vwap(candles)
        elif linea_ref == "EMA":
            if periodo <= 0:
                periodo = 20
            ema_values = self._calcular_ema(closes, periodo)
            valor_linea = ema_values[-1] if ema_values else 0
        elif linea_ref == "MA":
            if periodo <= 0:
                periodo = 20
            sma_values = self._calcular_sma(closes, periodo)
            valor_linea = sma_values[-1] if sma_values else 0
        else:
            return False

        if valor_linea == 0:
            return False

        if modo == "PORCENTAJE":
            distancia = ((precio_actual - valor_linea) / valor_linea) * 100
        else:
            distancia = precio_actual - valor_linea

        resultado = self._evaluar_condicion_completa(distancia, filtro)
        logger.debug(f"DISTANCE_FROM_{linea_ref}: dist={distancia:.2f} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        periodo = self._obtener_valor_int(filtro, "PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA")
        return max(periodo + 10, 200)
