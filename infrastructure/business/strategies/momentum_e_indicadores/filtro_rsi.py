"""Filtro: RSI (Relative Strength Index) - Indicador de momentum."""

import logging

from domain.models.candle import Candle
from domain.models.datos_fundamentales import DatosFundamentales
from domain.models.escaner import Filtro
from infrastructure.business.strategies.base_filtro import BaseFiltro

logger = logging.getLogger(__name__)


class FiltroRSI(BaseFiltro):

    def evaluar(self, candles: list[Candle], filtro: Filtro, datos_fundamentales: DatosFundamentales | None = None) -> bool:
        min_val, max_val = self._obtener_valor_condicional(filtro)
        if min_val is None:
            return False

        periodo = self._obtener_valor_int(filtro, "PERIODO_RSI") or 14

        closes = [c.close for c in candles]
        if len(closes) < periodo + 1:
            return False

        rsi = self._calcular_rsi(closes, periodo)
        if rsi is None:
            return False

        resultado = self._evaluar_condicion_completa(rsi, filtro)
        logger.debug(f"RSI: rsi={rsi:.2f} -> {resultado}")
        return resultado

    @staticmethod
    def _calcular_rsi(closes: list[float], periodo: int) -> float | None:
        """Calcula RSI usando metodo Wilder (EMA suavizada)."""
        if len(closes) < periodo + 1:
            return None

        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        gains = [d if d > 0 else 0 for d in deltas[:periodo]]
        losses = [-d if d < 0 else 0 for d in deltas[:periodo]]

        avg_gain = sum(gains) / periodo
        avg_loss = sum(losses) / periodo

        for d in deltas[periodo:]:
            gain = d if d > 0 else 0
            loss = -d if d < 0 else 0
            avg_gain = (avg_gain * (periodo - 1) + gain) / periodo
            avg_loss = (avg_loss * (periodo - 1) + loss) / periodo

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def get_timeframe_requerido(self, filtro: Filtro) -> str:
        tf = self._obtener_valor_string(filtro, "TIMEFRAME_RSI")
        return tf if tf else "M1"

    def get_cantidad_velas_requeridas(self, filtro: Filtro) -> int:
        periodo = self._obtener_valor_int(filtro, "PERIODO_RSI") or 14
        return periodo * 3
