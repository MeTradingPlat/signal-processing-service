"""Filtro: EMA/VWAP Support/Resistance - Detecta si EMA o VWAP actua como soporte/resistencia."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroEmaVwapSupportResistance(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        linea_ref = self._obtener_valor_string(filtro, "LINEA_REFERENCIA_EMA_VWAP_SUPPORT") or "VWAP"
        periodo_ema = self._obtener_valor_int(filtro, "PERIODO_EMA_EMA_VWAP_SUPPORT") or 20
        tipo_rol = self._obtener_valor_string(filtro, "TIPO_ROL_EMA_VWAP_SUPPORT") or "SOPORTE"

        if len(candles) < 3:
            return False

        closes = [c.close for c in candles]

        if linea_ref == "VWAP":
            valor_linea = self._calcular_vwap(candles)
        else:
            ema_values = self._calcular_ema(closes, periodo_ema)
            if not ema_values:
                return False
            valor_linea = ema_values[-1]

        ultima = candles[-1]

        if tipo_rol == "SOPORTE":
            # Precio rebota desde arriba de la linea
            resultado = ultima.low <= valor_linea and ultima.close > valor_linea
        else:  # RESISTENCIA
            # Precio rechazado desde abajo de la linea
            resultado = ultima.high >= valor_linea and ultima.close < valor_linea

        logger.debug(f"EMA_VWAP_{tipo_rol}: linea={valor_linea:.2f} close={ultima.close:.2f} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        periodo = self._obtener_valor_int(filtro, "PERIODO_EMA_EMA_VWAP_SUPPORT") or 20
        return periodo * 2
