"""Filtro: Break Over Recent Highs/Lows - Rompimiento de maximos/minimos recientes."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroBreakOverRecent(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 3:
            return False

        opcion = self._obtener_valor_string(filtro, "OPCION_EXTREMO_BREAK_OVER") or "HIGH"

        anteriores = candles[:-1]
        ultima = candles[-1]

        if opcion == "HIGH":
            nivel = max(c.high for c in anteriores)
            resultado = ultima.close > nivel
        else:
            nivel = min(c.low for c in anteriores)
            resultado = ultima.close < nivel

        logger.debug(f"BREAK_OVER ({opcion}): nivel={nivel:.2f} close={ultima.close:.2f} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_BREAK_OVER")
        return tf if tf else "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 50
