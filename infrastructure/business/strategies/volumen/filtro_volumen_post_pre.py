"""Filtro: Volumen Post/Pre market - TODO: requiere data de pre/post market."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroVolumenPostPre(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        # TODO: Implementar cuando se tenga data de pre/post market
        logger.debug("VOLUMEN_POST_PRE: TODO - No implementado aun")
        return True

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 50
