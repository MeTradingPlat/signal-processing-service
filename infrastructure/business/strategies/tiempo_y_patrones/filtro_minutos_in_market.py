"""Filtro: Minutos In Market - Evalua si han pasado N minutos desde apertura del mercado."""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)

NYSE_TZ = ZoneInfo("America/New_York")
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30


class FiltroMinutosInMarket(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        minutos_requeridos = self._obtener_valor_int(filtro, "MINUTOS_TRANSCURRIDOS")
        if minutos_requeridos <= 0:
            minutos_requeridos = 30

        now_ny = datetime.now(timezone.utc).astimezone(NYSE_TZ)
        market_open_ny = now_ny.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)

        minutos_transcurridos = (now_ny - market_open_ny).total_seconds() / 60

        resultado = minutos_transcurridos >= minutos_requeridos
        logger.debug(f"MINUTOS_IN_MARKET: transcurridos={minutos_transcurridos:.0f} requeridos={minutos_requeridos} -> {resultado}")
        return resultado

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        return "M1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        return 1
