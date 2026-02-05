"""Filtro: Relative Volume Same Time - TODO: requiere comparacion con misma hora historica."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroRelativeVolumeSameTime(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        # TODO: Implementar comparacion de volumen a la misma hora en dias anteriores
        logger.debug("RELATIVE_VOLUME_SAME_TIME: TODO - No implementado aun")
        return True

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 100
