"""Filtro: Volume Spike - Detecta picos de volumen respecto a velas anteriores."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroVolumeSpike(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        min_val, max_val = self._obtener_valor_condicional(filtro)
        num_velas = self._obtener_valor_int(filtro, "NUMERO_VELAS_VOLUME_SPIKE")
        proporcion = self._obtener_valor_float(filtro, "PROPORCION_VOLUMEN_VOLUME_SPIKE")

        if num_velas <= 0:
            num_velas = 10
        if proporcion <= 0:
            proporcion = 2.0

        if len(candles) < num_velas + 1:
            return False

        vol_actual = candles[-1].volume
        vol_anteriores = [c.volume for c in candles[-(num_velas + 1):-1]]
        avg_vol = sum(vol_anteriores) / len(vol_anteriores) if vol_anteriores else 1

        if avg_vol == 0:
            return False

        ratio = vol_actual / avg_vol
        resultado = ratio >= proporcion

        logger.debug(f"VOLUME_SPIKE: ratio={ratio:.2f} proporcion={proporcion} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_VOLUME_SPIKE")
        return tf if tf else "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        num_velas = self._obtener_valor_int(filtro, "NUMERO_VELAS_VOLUME_SPIKE")
        return max(num_velas + 1, 11)
