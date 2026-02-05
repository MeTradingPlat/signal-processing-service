"""Filtro: Bearish/Bullish Engulfing Candle - Patron de vela envolvente."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroBearishBullishEngulfing(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        tipo_patron = self._obtener_valor_string(filtro, "TIPO_PATRON_BEARISH_BULLISH_ENGULFING_CANDLE") or "ALCISTA"

        anterior = candles[-2]
        actual = candles[-1]

        if tipo_patron == "ALCISTA":
            # Bullish engulfing: vela anterior bajista, actual alcista que la envuelve
            resultado = (
                anterior.close < anterior.open and
                actual.close > actual.open and
                actual.open <= anterior.close and
                actual.close >= anterior.open
            )
        else:
            # Bearish engulfing: vela anterior alcista, actual bajista que la envuelve
            resultado = (
                anterior.close > anterior.open and
                actual.close < actual.open and
                actual.open >= anterior.close and
                actual.close <= anterior.open
            )

        logger.debug(f"ENGULFING ({tipo_patron}): -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_BEARISH_BULLISH_ENGULFING_CANDLE")
        return tf if tf else "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 2
