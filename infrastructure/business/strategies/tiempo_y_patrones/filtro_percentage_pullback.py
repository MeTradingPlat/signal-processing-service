"""Filtro: Percentage Pullback Highs/Lows - Detecta retroceso porcentual desde extremos."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroPercentagePullback(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        punto_ref = self._obtener_valor_string(filtro, "PUNTO_REFERENCIA_PULLBACK") or "HIGH"
        porcentaje = self._obtener_valor_float(filtro, "PORCENTAJE_RETROCESO_PULLBACK")
        if porcentaje <= 0:
            porcentaje = 5.0

        precio_actual = candles[-1].close

        if punto_ref == "HIGH":
            extremo = max(c.high for c in candles)
            if extremo == 0:
                return False
            retroceso = ((extremo - precio_actual) / extremo) * 100
        else:
            extremo = min(c.low for c in candles)
            if extremo == 0:
                return False
            retroceso = ((precio_actual - extremo) / extremo) * 100

        resultado = retroceso >= porcentaje
        logger.debug(f"PULLBACK ({punto_ref}): retroceso={retroceso:.2f}% umbral={porcentaje}% -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 78
