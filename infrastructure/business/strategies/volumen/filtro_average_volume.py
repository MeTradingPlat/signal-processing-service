"""Filtro: Average Volume - Evalua si el volumen promedio esta en rango."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroAverageVolume(BaseFiltro):

    DEFAULT_PERIODO = 20

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 1:
            return False

        volumes = [c.volume for c in candles]
        avg_volume = sum(volumes) / len(volumes)
        resultado = self._evaluar_condicion_completa(avg_volume, filtro)
        logger.debug(f"AVERAGE_VOLUME: avg={avg_volume:.0f} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_AVERAGE_VOLUME")
        return tf if tf else "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return self.DEFAULT_PERIODO
