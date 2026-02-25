"""Filtro: Volume - Evalua si el volumen de cierre esta dentro del rango condicional."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroVolume(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not candles:
            return False

        volumen = candles[-1].volume
        resultado = self._evaluar_condicion_completa(volumen, filtro)
        logger.debug(f"VOLUME: vol={volumen} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_VOLUME")
        return tf if tf else "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
