"""Ejecutor de filtros: evalua una lista de filtros sobre data de mercado."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro

logger = logging.getLogger(__name__)


MINIMO_BARRAS = 15


class FiltroExecutor:

    def __init__(self, obj_filtro_registry):
        self.obj_filtro_registry = obj_filtro_registry

    def ejecutar_filtros(
        self,
        filtros: list[Filtro],
        candles_por_timeframe: dict[str, list[Candle]],
        simbolo: str,
        datos_fundamentales: DatosFundamentales | None = None,
    ) -> bool:
        """
        Ejecuta todos los filtros. Retorna True solo si TODOS pasan.
        Cortocircuita en el primer filtro que falle.
        """
        for filtro in filtros:
            impl = self.obj_filtro_registry.obtener_filtro(filtro.enum_filtro)
            if impl is None:
                logger.warning(f"Filtro no implementado: {filtro.enum_filtro}")
                continue

            tf = impl.get_timeframe_requerido(filtro)
            candles = candles_por_timeframe.get(tf, [])

            if not candles:
                logger.debug(f"Sin data para {simbolo} tf={tf}, filtro={filtro.enum_filtro}")
                return False

            try:
                resultado = impl.evaluar(candles, filtro, datos_fundamentales)
                if not resultado:
                    logger.debug(f"Filtro {filtro.enum_filtro} NO paso para {simbolo}")
                    return False
                logger.debug(f"Filtro {filtro.enum_filtro} PASO para {simbolo}")
            except Exception as e:
                logger.error(f"Error en filtro {filtro.enum_filtro} para {simbolo}: {e}")
                return False

        return True

    def obtener_timeframes_necesarios(self, filtros: list[Filtro]) -> dict[str, int]:
        """
        Retorna un dict de timeframe -> max cantidad de velas necesarias
        combinando los requerimientos de todos los filtros.
        """
        timeframes = {}
        for filtro in filtros:
            impl = self.obj_filtro_registry.obtener_filtro(filtro.enum_filtro)
            if impl is None:
                continue
            tf = impl.get_timeframe_requerido(filtro)
            cantidad = max(impl.get_cantidad_velas_requeridas(filtro), MINIMO_BARRAS)
            if tf in timeframes:
                timeframes[tf] = max(timeframes[tf], cantidad)
            else:
                timeframes[tf] = cantidad

        if not timeframes:
            timeframes["M5"] = max(100, MINIMO_BARRAS)

        return timeframes
