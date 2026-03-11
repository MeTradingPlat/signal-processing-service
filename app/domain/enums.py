from enum import Enum


class EnumEstadoEscaner(str, Enum):
    DETENIDO = "DETENIDO"
    INICIADO = "INICIADO"
    ARCHIVADO = "ARCHIVADO"
    DESARCHIVADO = "DESARCHIVADO"


class EnumTipoEjecucion(str, Enum):
    UNA_VEZ = "UNA_VEZ"
    DIARIA = "DIARIA"


class EnumCondicional(str, Enum):
    MAYOR_QUE = "MAYOR_QUE"
    MENOR_QUE = "MENOR_QUE"
    ENTRE = "ENTRE"
    FUERA = "FUERA"
    IGUAL_A = "IGUAL_A"


class EnumTipoValor(str, Enum):
    CONDICIONAL = "CONDICIONAL"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"


class EnumTimeframe(str, Enum):
    """Timeframes soportados (solo los nativos de marketdata-service)."""
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"


# Mapeo de nombre de timeframe en scanner-management → EnumTimeframe de marketdata
SCANNER_TF_A_MARKETDATA: dict[str, EnumTimeframe] = {
    "_1M": EnumTimeframe.M1,
    "_5M": EnumTimeframe.M5,
    "_15M": EnumTimeframe.M15,
    "_30M": EnumTimeframe.M30,
    "_1H": EnumTimeframe.H1,
}

# Intervalo en segundos por timeframe
TIMEFRAME_INTERVALO_SEG: dict[EnumTimeframe, int] = {
    EnumTimeframe.M1: 60,
    EnumTimeframe.M5: 300,
    EnumTimeframe.M15: 900,
    EnumTimeframe.M30: 1800,
    EnumTimeframe.H1: 3600,
}


class EnumFiltro(str, Enum):
    VOLUME = "VOLUME"
    AVERAGE_VOLUME = "AVERAGE_VOLUME"
    RELATIVE_VOLUME = "RELATIVE_VOLUME"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    CHANGE = "CHANGE"
    PERCENTAGE_CHANGE = "PERCENTAGE_CHANGE"
    PRECIO = "PRECIO"
    GAP_FROM_CLOSE = "GAP_FROM_CLOSE"
    POSITION_IN_RANGE = "POSITION_IN_RANGE"
    RANGE_DOLLARS = "RANGE_DOLLARS"
    ATR = "ATR"
    ATRP = "ATRP"
    RELATIVE_RANGE = "RELATIVE_RANGE"
    RSI = "RSI"
    DISTANCE_FROM_VWAP = "DISTANCE_FROM_VWAP"
    DISTANCE_FROM_EMA = "DISTANCE_FROM_EMA"
    DISTANCE_FROM_MA = "DISTANCE_FROM_MA"
    EMA_VWAP_SUPPORT_RESISTANCE = "EMA_VWAP_SUPPORT_RESISTANCE"
    BEARISH_BULLISH_ENGULFING = "BEARISH_BULLISH_ENGULFING"
    CONSECUTIVE_CANDLES = "CONSECUTIVE_CANDLES"
    FIRST_CANDLE = "FIRST_CANDLE"
    OPENING_RANGE_BREAKOUT = "OPENING_RANGE_BREAKOUT"
    PIVOTS = "PIVOTS"
    FLOAT = "FLOAT"
    MARKET_CAP = "MARKET_CAP"
    SHORT_INTEREST = "SHORT_INTEREST"
    DAYS_UNTIL_EARNINGS = "DAYS_UNTIL_EARNINGS"
    NOTICIAS = "NOTICIAS"
