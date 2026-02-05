"""Filtro: Halt - Detecta si un simbolo esta en halt (suspension de trading)."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroHalt(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if not datos_fundamentales or not datos_fundamentales.halt_status:
            return False

        valor_esperado = self._obtener_valor_string(filtro, "VALOR_HALT")
        if not valor_esperado:
            return bool(datos_fundamentales.halt_status)

        return datos_fundamentales.halt_status == valor_esperado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
