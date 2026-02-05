"""Filtro: Noticias - Evalua si el estado de noticias coincide con el configurado."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroNoticias(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not datos_fundamentales or not datos_fundamentales.estado_noticia:
            logger.debug("NOTICIAS: sin datos fundamentales disponibles")
            return True

        estado_requerido = self._obtener_valor_string(filtro, "ESTADO_NOTICIA") or "NINGUNA"

        resultado = datos_fundamentales.estado_noticia == estado_requerido
        logger.debug(f"NOTICIAS: estado={datos_fundamentales.estado_noticia} requerido={estado_requerido} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
