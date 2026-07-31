from datetime import datetime, timezone

from app.models.enums import EnumFiltro, EnumParametro
from app.models.filtro import Filtro
from app.models.valor import ValorInteger, ValorString

_DEFAULT_TIMEFRAME = "1M"
_MIN_BARS_FLOOR = 150

# Filtros cuyo calculo depende de un periodo configurable (EMA/RSI/ATR...) --
# (parametro que trae el periodo, default si no viene, margen de barras
# extra sobre el periodo para que el indicador converja de verdad en vez de
# apenas producir un valor). 3x es la regla practica estandar para EMA/RSI/
# ATR: con exactamente "periodo" barras el valor inicial existe pero esta
# lejos de estabilizarse.
_PERIOD_PARAMS: dict[EnumFiltro, tuple[EnumParametro, int, int]] = {
    EnumFiltro.RSI: (EnumParametro.PERIODO_RSI, 14, 3),
    EnumFiltro.ATR: (EnumParametro.LONGITUD_ATR, 14, 3),
    EnumFiltro.ATRP: (EnumParametro.PERIODO_ATR_ATRP, 14, 3),
    EnumFiltro.DISTANCE_FROM_VWAP: (EnumParametro.PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA, 9, 3),
    EnumFiltro.DISTANCE_FROM_EMA: (EnumParametro.PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA, 9, 3),
    EnumFiltro.DISTANCE_FROM_MA: (EnumParametro.PERIODO_LINEA_DISTANCE_FROM_VWAP_EMA_MA, 20, 3),
    EnumFiltro.BACK_TO_EMA_ALERT: (EnumParametro.PERIODO_EMA_BACK_TO_EMA, 9, 3),
    EnumFiltro.THROUGH_EMA_VWAP_ALERT: (EnumParametro.THROUGH_EMA_VWAP_PERIODO_EMA, 9, 3),
    EnumFiltro.EMA_VWAP_SUPPORT_RESISTANCE: (EnumParametro.PERIODO_EMA_EMA_VWAP_SUPPORT, 9, 3),
}

# Filtros que necesitan un numero fijo de barras sin importar ningun
# parametro de periodo (leidos directo del codigo de cada estrategia).
_FIXED_LOOKBACK: dict[EnumFiltro, int] = {
    EnumFiltro.PERCENTAGE_PULLBACK_HIGHS_LOWS: 5,
    EnumFiltro.PIVOTS: 3,
    EnumFiltro.BEARISH_BULLISH_ENGULFING: 2,
    EnumFiltro.NEW_CANDLE_HIGH_LOW: 2,
    EnumFiltro.BREAK_OVER_RECENT_HIGHS_LOWS: 2,
}

# Filtros que solo miran las velas de HOY (_todays_candles): necesitan
# suficientes barras para cubrir desde medianoche UTC hasta ahora, o en
# timeframes finos (M1-M10) el piso fijo de abajo no alcanza a llegar hasta
# la apertura real del dia y el filtro compara contra una vela que no es en
# verdad la primera del dia.
_DAY_ANCHORED: set[EnumFiltro] = {
    EnumFiltro.HIGH_LOW_OF_DAY,
    EnumFiltro.OPENING_RANGE_BREAKOUT,
    EnumFiltro.OPENING_RANGE_BREAKDOWN,
    EnumFiltro.FIRST_CANDLE,
}

# Filtros que comparan la vela actual contra la misma franja horaria en N
# dias anteriores -- necesitan cubrir dias COMPLETOS hacia atras, no solo
# el de hoy. El numero debe coincidir con el _DIAS_COMPARACION de cada
# estrategia correspondiente.
_MULTI_DAY_COMPARISON: dict[EnumFiltro, int] = {
    EnumFiltro.RELATIVE_VOLUME_SAME_TIME: 5,
}
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


def _leer_periodo(filtro: Filtro, param_enum: EnumParametro, default: int) -> int:
    for p in filtro.parametros:
        if p.enumParametro == param_enum and isinstance(p.objValorSeleccionado, ValorInteger):
            return p.objValorSeleccionado.valor or default
    return default


def _barras_para_cubrir_hoy(minutos: int) -> int:
    ahora = datetime.now(timezone.utc)
    minutos_desde_medianoche = ahora.hour * 60 + ahora.minute
    return (minutos_desde_medianoche // minutos) + 5


def _barras_para_cubrir_dias(minutos: int, dias: int) -> int:
    barras_hoy = _barras_para_cubrir_hoy(minutos)
    barras_por_dia_completo = 1440 // minutos
    return barras_hoy + dias * barras_por_dia_completo


def bars_requeridas_filtro(filtro: Filtro, minutos: int) -> int:
    """Cuantas barras necesita ESTE filtro para producir un valor valido y
    estable, segun su propio periodo/config -- no un numero fijo por
    timeframe que ignora si el filtro es un RSI(14) o un RSI(200)."""
    enum_filtro = filtro.enumFiltro
    if enum_filtro in _PERIOD_PARAMS:
        param_enum, default_periodo, margen = _PERIOD_PARAMS[enum_filtro]
        periodo = _leer_periodo(filtro, param_enum, default_periodo)
        return periodo * margen
    if enum_filtro == EnumFiltro.CONSECUTIVE_CANDLES:
        return _leer_periodo(filtro, EnumParametro.NUMERO_VELAS_CONSECUTIVAS, 3) + 1
    if enum_filtro in _FIXED_LOOKBACK:
        return _FIXED_LOOKBACK[enum_filtro]
    if enum_filtro in _DAY_ANCHORED:
        return _barras_para_cubrir_hoy(minutos)
    if enum_filtro in _MULTI_DAY_COMPARISON:
        return _barras_para_cubrir_dias(minutos, _MULTI_DAY_COMPARISON[enum_filtro])
    return 0


def bars_necesarias_grupo(filtros: list[Filtro], minutos: int) -> int:
    """bars_needed para un grupo de filtros que comparten timeframe: el piso
    historico de siempre, o lo que el filtro mas exigente del grupo necesite
    de verdad, lo que sea mayor."""
    requeridas = max((bars_requeridas_filtro(f, minutos) for f in filtros), default=0)
    return max(_MIN_BARS_FLOOR, minutos * 2, requeridas)
