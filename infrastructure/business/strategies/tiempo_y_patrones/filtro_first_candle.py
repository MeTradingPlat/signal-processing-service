"""Filtro: First Candle - Evalua si la primera vela del dia es alcista o bajista."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroFirstCandle(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not candles:
            return False

        tipo_vela = self._obtener_valor_string(filtro, "TIPO_VELA_FIRTS_CANDLE") or "ALCISTA"

        primera = candles[0]
        if tipo_vela == "ALCISTA":
            resultado = primera.close > primera.open
        else:
            resultado = primera.close < primera.open

        logger.debug(f"FIRST_CANDLE ({tipo_vela}): o={primera.open} c={primera.close} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
