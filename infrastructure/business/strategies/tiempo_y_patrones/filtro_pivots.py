"""Filtro: Pivots - Evalua niveles de pivot points."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroPivots(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        if len(candles) < 2:
            return False

        # Calcula pivot point clasico usando la vela anterior (dia anterior)
        prev = candles[-2]
        pivot = (prev.high + prev.low + prev.close) / 3
        r1 = 2 * pivot - prev.low
        s1 = 2 * pivot - prev.high

        precio_actual = candles[-1].close

        # Detecta si el precio esta cerca de un nivel de pivot (dentro del 0.5%)
        tolerancia = pivot * 0.005
        cerca_pivot = abs(precio_actual - pivot) <= tolerancia
        cerca_r1 = abs(precio_actual - r1) <= tolerancia
        cerca_s1 = abs(precio_actual - s1) <= tolerancia

        resultado = cerca_pivot or cerca_r1 or cerca_s1
        logger.debug(f"PIVOTS: P={pivot:.2f} R1={r1:.2f} S1={s1:.2f} close={precio_actual:.2f} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_PIVOTS")
        return tf if tf else "D1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 2
