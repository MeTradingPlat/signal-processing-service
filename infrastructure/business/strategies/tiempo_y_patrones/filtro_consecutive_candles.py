"""Filtro: Consecutive Candles - Detecta N velas consecutivas alcistas o bajistas."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroConsecutiveCandles(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        num_velas = self._obtener_valor_int(filtro, "NUMERO_VELAS_CONSECUTIVAS")
        if num_velas <= 0:
            num_velas = 3

        if len(candles) < num_velas:
            return False

        ultimas = candles[-num_velas:]

        todas_alcistas = all(c.close > c.open for c in ultimas)
        todas_bajistas = all(c.close < c.open for c in ultimas)

        resultado = todas_alcistas or todas_bajistas
        tipo = "alcistas" if todas_alcistas else ("bajistas" if todas_bajistas else "mixtas")
        logger.debug(f"CONSECUTIVE_CANDLES: {num_velas} velas {tipo} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_CONSECUTIVE_CANDLES")
        return tf if tf else "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        num = self._obtener_valor_int(filtro, "NUMERO_VELAS_CONSECUTIVAS") or 3
        return num + 1
