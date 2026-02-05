"""Registry: mapea EnumFiltro a su implementacion concreta."""

import logging

from infrastructure.business.strategies.base_filtro import BaseFiltro

# Volumen
from infrastructure.business.strategies.volumen.filtro_volume import FiltroVolume
from infrastructure.business.strategies.volumen.filtro_average_volume import FiltroAverageVolume
from infrastructure.business.strategies.volumen.filtro_volumen_post_pre import FiltroVolumenPostPre
from infrastructure.business.strategies.volumen.filtro_relative_volume import FiltroRelativeVolume
from infrastructure.business.strategies.volumen.filtro_relative_volume_same_time import FiltroRelativeVolumeSameTime
from infrastructure.business.strategies.volumen.filtro_volume_spike import FiltroVolumeSpike

# Precio y Movimiento
from infrastructure.business.strategies.precio_y_movimiento.filtro_precio import FiltroPrecio
from infrastructure.business.strategies.precio_y_movimiento.filtro_change import FiltroChange
from infrastructure.business.strategies.precio_y_movimiento.filtro_percentage_change import FiltroPercentageChange
from infrastructure.business.strategies.precio_y_movimiento.filtro_gap_from_close import FiltroGapFromClose
from infrastructure.business.strategies.precio_y_movimiento.filtro_position_in_range import FiltroPositionInRange
from infrastructure.business.strategies.precio_y_movimiento.filtro_percentage_range import FiltroPercentageRange
from infrastructure.business.strategies.precio_y_movimiento.filtro_range_dollars import FiltroRangeDollars
from infrastructure.business.strategies.precio_y_movimiento.filtro_crossing_above_below import FiltroCrossingAboveBelow
from infrastructure.business.strategies.precio_y_movimiento.filtro_distance_from_vwap_ema_ma import FiltroDistanceFromVwapEmaMa

# Volatilidad
from infrastructure.business.strategies.volatilidad.filtro_atr import FiltroATR
from infrastructure.business.strategies.volatilidad.filtro_atrp import FiltroATRP
from infrastructure.business.strategies.volatilidad.filtro_relative_range import FiltroRelativeRange

# Momentum e Indicadores
from infrastructure.business.strategies.momentum_e_indicadores.filtro_rsi import FiltroRSI
from infrastructure.business.strategies.momentum_e_indicadores.filtro_back_to_ema_alert import FiltroBackToEmaAlert
from infrastructure.business.strategies.momentum_e_indicadores.filtro_through_ema_vwap_alert import FiltroThroughEmaVwapAlert
from infrastructure.business.strategies.momentum_e_indicadores.filtro_ema_vwap_support_resistance import FiltroEmaVwapSupportResistance

# Tiempo y Patrones
from infrastructure.business.strategies.tiempo_y_patrones.filtro_halt import FiltroHalt
from infrastructure.business.strategies.tiempo_y_patrones.filtro_consecutive_candles import FiltroConsecutiveCandles
from infrastructure.business.strategies.tiempo_y_patrones.filtro_bearish_bullish_engulfing import FiltroBearishBullishEngulfing
from infrastructure.business.strategies.tiempo_y_patrones.filtro_first_candle import FiltroFirstCandle
from infrastructure.business.strategies.tiempo_y_patrones.filtro_high_low_of_day import FiltroHighLowOfDay
from infrastructure.business.strategies.tiempo_y_patrones.filtro_new_candle_high_low import FiltroNewCandleHighLow
from infrastructure.business.strategies.tiempo_y_patrones.filtro_percentage_pullback import FiltroPercentagePullback
from infrastructure.business.strategies.tiempo_y_patrones.filtro_break_over_recent import FiltroBreakOverRecent
from infrastructure.business.strategies.tiempo_y_patrones.filtro_opening_range_breakdown import FiltroOpeningRangeBreakdown
from infrastructure.business.strategies.tiempo_y_patrones.filtro_opening_range_breakout import FiltroOpeningRangeBreakout
from infrastructure.business.strategies.tiempo_y_patrones.filtro_pivots import FiltroPivots
from infrastructure.business.strategies.tiempo_y_patrones.filtro_minutos_in_market import FiltroMinutosInMarket

# Fundamentales
from infrastructure.business.strategies.fundamentales.filtro_float import FiltroFloat
from infrastructure.business.strategies.fundamentales.filtro_shares_outstanding import FiltroSharesOutstanding
from infrastructure.business.strategies.fundamentales.filtro_market_cap import FiltroMarketCap
from infrastructure.business.strategies.fundamentales.filtro_short_interest import FiltroShortInterest
from infrastructure.business.strategies.fundamentales.filtro_short_ratio import FiltroShortRatio
from infrastructure.business.strategies.fundamentales.filtro_days_until_earnings import FiltroDaysUntilEarnings
from infrastructure.business.strategies.fundamentales.filtro_noticias import FiltroNoticias

logger = logging.getLogger(__name__)

EVENT_FILTERS = frozenset({
    "CROSSING_ABOVE_BELOW",
    "BREAK_OVER_RECENT_HIGHS_LOWS",
    "HIGH_LOW_OF_DAY",
    "NEW_CANDLE_HIGH_LOW",
    "OPENING_RANGE_BREAKOUT",
    "OPENING_RANGE_BREAKDOWN",
    "BACK_TO_EMA_ALERT",
    "THROUGH_EMA_VWAP_ALERT",
    "HALT",
})


class FiltroRegistry:
    """Registra y proporciona acceso O(1) a las implementaciones de filtros."""

    def __init__(self):
        self._registry: dict[str, BaseFiltro] = {}
        self._registrar_todos()

    def _registrar_todos(self) -> None:
        filtros = {
            # Volumen
            "VOLUME": FiltroVolume(),
            "AVERAGE_VOLUME": FiltroAverageVolume(),
            "VOLUMEN_POST_PRE": FiltroVolumenPostPre(),
            "RELATIVE_VOLUME": FiltroRelativeVolume(),
            "RELATIVE_VOLUME_SAME_TIME": FiltroRelativeVolumeSameTime(),
            "VOLUME_SPIKE": FiltroVolumeSpike(),
            # Precio y Movimiento
            "PRECIO": FiltroPrecio(),
            "CHANGE": FiltroChange(),
            "PERCENTAGE_CHANGE": FiltroPercentageChange(),
            "GAP_FROM_CLOSE": FiltroGapFromClose(),
            "POSITION_IN_RANGE": FiltroPositionInRange(),
            "PERCENTAGE_RANGE": FiltroPercentageRange(),
            "RANGE_DOLLARS": FiltroRangeDollars(),
            "CROSSING_ABOVE_BELOW": FiltroCrossingAboveBelow(),
            "DISTANCE_FROM_VWAP": FiltroDistanceFromVwapEmaMa(),
            "DISTANCE_FROM_EMA": FiltroDistanceFromVwapEmaMa(),
            "DISTANCE_FROM_MA": FiltroDistanceFromVwapEmaMa(),
            # Volatilidad
            "ATR": FiltroATR(),
            "ATRP": FiltroATRP(),
            "RELATIVE_RANGE": FiltroRelativeRange(),
            # Momentum
            "RSI": FiltroRSI(),
            "BACK_TO_EMA_ALERT": FiltroBackToEmaAlert(),
            "THROUGH_EMA_VWAP_ALERT": FiltroThroughEmaVwapAlert(),
            "EMA_VWAP_SUPPORT_RESISTANCE": FiltroEmaVwapSupportResistance(),
            # Tiempo y Patrones
            "HALT": FiltroHalt(),
            "CONSECUTIVE_CANDLES": FiltroConsecutiveCandles(),
            "BEARISH_BULLISH_ENGULFING": FiltroBearishBullishEngulfing(),
            "FIRST_CANDLE": FiltroFirstCandle(),
            "HIGH_LOW_OF_DAY": FiltroHighLowOfDay(),
            "NEW_CANDLE_HIGH_LOW": FiltroNewCandleHighLow(),
            "PERCENTAGE_PULLBACK_HIGHS_LOWS": FiltroPercentagePullback(),
            "BREAK_OVER_RECENT_HIGHS_LOWS": FiltroBreakOverRecent(),
            "OPENING_RANGE_BREAKDOWN": FiltroOpeningRangeBreakdown(),
            "OPENING_RANGE_BREAKOUT": FiltroOpeningRangeBreakout(),
            "PIVOTS": FiltroPivots(),
            "MINUTOS_IN_MARKET": FiltroMinutosInMarket(),
            # Fundamentales
            "FLOAT": FiltroFloat(),
            "SHARES_OUTSTANDING": FiltroSharesOutstanding(),
            "MARKET_CAP": FiltroMarketCap(),
            "SHORT_INTEREST": FiltroShortInterest(),
            "SHORT_RATIO": FiltroShortRatio(),
            "DAYS_UNTIL_EARNINGS": FiltroDaysUntilEarnings(),
            "NOTICIAS": FiltroNoticias(),
        }
        self._registry = filtros
        logger.info(f"Filtros registrados: {len(self._registry)}")

    def obtener_filtro(self, enum_filtro: str) -> BaseFiltro | None:
        return self._registry.get(enum_filtro)

    def clasificar_filtros(self, filtros) -> tuple[list, list]:
        """Separa filtros en (state_filters, event_filters)."""
        state, event = [], []
        for f in filtros:
            (event if f.enum_filtro in EVENT_FILTERS else state).append(f)
        return state, event
