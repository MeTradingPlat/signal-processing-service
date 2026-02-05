"""Filtro: Through EMA/VWAP Alert - Detecta rompimiento a traves de EMA o VWAP."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroThroughEmaVwapAlert(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        linea_cruce = self._obtener_valor_string(filtro, "THROUGH_EMA_VWAP_LINEA_CRUCE") or "EMA"
        periodo_ema = self._obtener_valor_int(filtro, "THROUGH_EMA_VWAP_PERIODO_EMA") or 20
        direccion = self._obtener_valor_string(filtro, "THROUGH_EMA_VWAP_DIRECCION_ROMPIMIENTO") or "ALCISTA"

        if len(candles) < 3:
            return False

        closes = [c.close for c in candles]

        if linea_cruce == "VWAP":
            valor_linea_anterior = self._calcular_vwap(candles[:-1])
            valor_linea_actual = self._calcular_vwap(candles)
        else:
            ema_values = self._calcular_ema(closes, periodo_ema)
            if len(ema_values) < 2:
                return False
            valor_linea_anterior = ema_values[-2]
            valor_linea_actual = ema_values[-1]

        precio_anterior = candles[-2].close
        precio_actual = candles[-1].close

        if direccion == "ALCISTA":
            resultado = precio_anterior <= valor_linea_anterior and precio_actual > valor_linea_actual
        else:
            resultado = precio_anterior >= valor_linea_anterior and precio_actual < valor_linea_actual

        logger.debug(f"THROUGH_{linea_cruce}: dir={direccion} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        periodo = self._obtener_valor_int(filtro, "THROUGH_EMA_VWAP_PERIODO_EMA") or 20
        return periodo * 2
