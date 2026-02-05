"""Filtro: New Candle High/Low - Detecta nueva vela que hace high o low."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroNewCandleHighLow(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        opcion = self._obtener_valor_string(filtro, "OPCION_EXTREMO_NEW_CANDLE") or "HIGH"
        ultima = candles[-1]
        penultima = candles[-2]

        if opcion == "HIGH":
            resultado = ultima.high > penultima.high
        else:
            resultado = ultima.low < penultima.low

        logger.debug(f"NEW_CANDLE_HIGH_LOW ({opcion}): -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_NEW_CANDLE")
        return tf if tf else "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 2
