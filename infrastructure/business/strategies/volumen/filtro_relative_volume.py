"""Filtro: Relative Volume - Compara volumen actual vs promedio historico."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroRelativeVolume(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        vol_actual = candles[-1].volume
        vol_historico = [c.volume for c in candles[:-1]]
        avg_vol = sum(vol_historico) / len(vol_historico) if vol_historico else 1

        if avg_vol == 0:
            return False

        rvol = (vol_actual / avg_vol) * 100
        resultado = self._evaluar_condicion_completa(rvol, filtro)
        logger.debug(f"RELATIVE_VOLUME: rvol={rvol:.1f}% -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_RELATIVE_VOLUME_PERCENT")
        return tf if tf else "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 21
