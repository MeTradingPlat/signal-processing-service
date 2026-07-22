from app.models.enums import EnumFiltro, EnumParametro
from app.models.filtro import Filtro
from app.models.valor import ValorString

_DEFAULT_TIMEFRAME = "1M"
_TIMEFRAME_MINUTES: dict[str, int] = {
    "1M": 1, "2M": 2, "3M": 3, "5M": 5, "10M": 10,
    "15M": 15, "30M": 30, "45M": 45,
    "1H": 60, "2H": 120, "3H": 180, "4H": 240, "12H": 720,
    "1D": 1440, "2D": 2880, "3D": 4320, "1W": 10080,
    "1MO": 43200, "3MO": 129600, "6MO": 259200, "1Y": 525600,
}

_TIMEFRAME_PARAMS: dict[EnumFiltro, EnumParametro] = {
    EnumFiltro.RSI: EnumParametro.TIMEFRAME_RSI,
    EnumFiltro.ATR: EnumParametro.TIMEFRAME_ATR,
    EnumFiltro.ATRP: EnumParametro.TIMEFRAME_ATRP,
    EnumFiltro.VOLUME: EnumParametro.TIMEFRAME_VOLUME,
    EnumFiltro.AVERAGE_VOLUME: EnumParametro.TIMEFRAME_AVERAGE_VOLUME,
    EnumFiltro.RELATIVE_VOLUME: EnumParametro.TIMEFRAME_RELATIVE_VOLUME_PERCENT,
    EnumFiltro.RELATIVE_VOLUME_SAME_TIME: EnumParametro.TIMEFRAME_RELATIVE_VOLUME_PERCENT,
    EnumFiltro.VOLUME_SPIKE: EnumParametro.TIMEFRAME_VOLUME_SPIKE,
    EnumFiltro.PERCENTAGE_CHANGE: EnumParametro.TIMEFRAME_PERCENTAGE_CHANGE_PERCENT,
    EnumFiltro.POSITION_IN_RANGE: EnumParametro.TIMEFRAME_POSITION_IN_RANGE,
    EnumFiltro.PERCENTAGE_RANGE: EnumParametro.TIMEFRAME_PERCENTAGE_RANGE_PERCENT,
    EnumFiltro.RANGE_DOLLARS: EnumParametro.TIMEFRAME_RANGE_DOLLAR,
    EnumFiltro.BACK_TO_EMA_ALERT: EnumParametro.TIMEFRAME_BACK_TO_EMA,
    EnumFiltro.DISTANCE_FROM_EMA: EnumParametro.TIMEFRAME_BACK_TO_EMA,
    EnumFiltro.DISTANCE_FROM_MA: EnumParametro.TIMEFRAME_BACK_TO_EMA,
    EnumFiltro.DISTANCE_FROM_VWAP: EnumParametro.TIMEFRAME_BACK_TO_EMA,
    EnumFiltro.BEARISH_BULLISH_ENGULFING: EnumParametro.TIMEFRAME_BEARISH_BULLISH_ENGULFING_CANDLE,
    EnumFiltro.CONSECUTIVE_CANDLES: EnumParametro.TIMEFRAME_CONSECUTIVE_CANDLES,
    EnumFiltro.NEW_CANDLE_HIGH_LOW: EnumParametro.TIMEFRAME_NEW_CANDLE,
    EnumFiltro.HIGH_LOW_OF_DAY: EnumParametro.TIMEFRAME_HIGH_LOW_DAY,
    EnumFiltro.BREAK_OVER_RECENT_HIGHS_LOWS: EnumParametro.TIMEFRAME_BREAK_OVER,
    EnumFiltro.OPENING_RANGE_BREAKOUT: EnumParametro.TIMEFRAME_OPENING_RANGE_BREAKOUT,
    EnumFiltro.OPENING_RANGE_BREAKDOWN: EnumParametro.TIMEFRAME_OPENING_RANGE_BREAKDOWN,
    EnumFiltro.PIVOTS: EnumParametro.TIMEFRAME_PIVOTS,
}


def extraer_timeframe_minutos(filtro: Filtro) -> int:
    param_enum = _TIMEFRAME_PARAMS.get(filtro.enumFiltro)
    if param_enum is None:
        return 1
    for p in filtro.parametros:
        if p.enumParametro == param_enum:
            if isinstance(p.objValorSeleccionado, ValorString):
                tf = p.objValorSeleccionado.valor or _DEFAULT_TIMEFRAME
                return _TIMEFRAME_MINUTES.get(tf.lstrip("_"), 1)
    return 1


def agrupar_por_timeframe(filtros: list[Filtro]) -> dict[int, list[Filtro]]:
    grupos: dict[int, list[Filtro]] = {}
    for f in filtros:
        minutos = extraer_timeframe_minutos(f)
        if minutos not in grupos:
            grupos[minutos] = []
        grupos[minutos].append(f)
    return grupos
