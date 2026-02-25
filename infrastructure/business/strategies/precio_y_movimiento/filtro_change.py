"""Filtro: Change - Evalua el cambio de precio respecto a un punto de referencia."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroChange(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        punto_ref = self._obtener_valor_string(filtro, "PUNTO_REFERENCIA_CHANGE") or "CLOSE"
        tipo_medida = self._obtener_valor_string(filtro, "TIPO_MEDIDA_CHANGE") or "PRECIO"

        precio_actual = candles[-1].close
        precio_referencia = candles[-2].close  # Default: cierre anterior

        if punto_ref == "OPEN":
            precio_referencia = candles[-1].open

        cambio = precio_actual - precio_referencia
        if tipo_medida == "PORCENTAJE" and precio_referencia != 0:
            cambio = (cambio / precio_referencia) * 100

        resultado = self._evaluar_condicion_completa(cambio, filtro)
        logger.debug(f"CHANGE: cambio={cambio:.4f} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M5"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 2
