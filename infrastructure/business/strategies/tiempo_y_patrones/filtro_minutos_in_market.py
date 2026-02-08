"""Filtro: Minutos In Market - Evalua si han pasado N minutos desde apertura del mercado."""

import logging
from datetime import datetime, timezone

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)

# Market open: 9:30 AM ET = 14:30 UTC
# NOTA: Este valor está hardcodeado en UTC porque el mercado NYSE opera en ET (Eastern Time)
# El horario de apertura es 9:30 AM ET, que equivale a 14:30 UTC (sin daylight saving)
# IMPORTANTE: Cuando se implemente Market Calendar Service, estos valores vendrán de la base de datos
# y se ajustarán automáticamente según el mercado y considerando daylight saving time
MARKET_OPEN_HOUR_UTC = 14
MARKET_OPEN_MINUTE_UTC = 30


class FiltroMinutosInMarket(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        minutos_requeridos = self._obtener_valor_int(filtro, "MINUTOS_TRANSCURRIDOS")
        if minutos_requeridos <= 0:
            minutos_requeridos = 30

        now = datetime.now(timezone.utc)
        market_open = now.replace(hour=MARKET_OPEN_HOUR_UTC, minute=MARKET_OPEN_MINUTE_UTC, second=0, microsecond=0)

        minutos_transcurridos = (now - market_open).total_seconds() / 60

        resultado = minutos_transcurridos >= minutos_requeridos
        logger.debug(f"MINUTOS_IN_MARKET: transcurridos={minutos_transcurridos:.0f} requeridos={minutos_requeridos} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
