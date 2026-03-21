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
    """Timeframes soportados por marketdata-service."""
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    D1 = "D1"
    W1 = "W1"
    MO1 = "MO1"


# Mapeo de nombre de timeframe en scanner-management → EnumTimeframe de marketdata.
# Se aceptan tanto el nombre del enum Java (e.g. "_1M") como la clave i18n
# (e.g. "timeframe.1m") que puede venir en el campo etiqueta del API.
SCANNER_TF_A_MARKETDATA: dict[str, EnumTimeframe] = {
    # Nombres de enum Java (EnumTimeframe.name())
    "_1M": EnumTimeframe.M1,
    "_5M": EnumTimeframe.M5,
    "_15M": EnumTimeframe.M15,
    "_30M": EnumTimeframe.M30,
    "_1H": EnumTimeframe.H1,
    "_1D": EnumTimeframe.D1,
    "_1W": EnumTimeframe.W1,
    "_1MO": EnumTimeframe.MO1,
    # Claves i18n (EnumTimeframe.getEtiqueta()) — fallback por si la API
    # serializa el campo etiqueta en lugar del valor enum.
    "timeframe.1m": EnumTimeframe.M1,
    "timeframe.5m": EnumTimeframe.M5,
    "timeframe.15m": EnumTimeframe.M15,
    "timeframe.30m": EnumTimeframe.M30,
    "timeframe.1h": EnumTimeframe.H1,
    "timeframe.1d": EnumTimeframe.D1,
    "timeframe.1w": EnumTimeframe.W1,
    "timeframe.1mo": EnumTimeframe.MO1,
}

# Intervalo en segundos por timeframe
TIMEFRAME_INTERVALO_SEG: dict[EnumTimeframe, int] = {
    EnumTimeframe.M1: 60,
    EnumTimeframe.M5: 300,
    EnumTimeframe.M15: 900,
    EnumTimeframe.M30: 1800,
    EnumTimeframe.H1: 3600,
    EnumTimeframe.D1: 86400,
    EnumTimeframe.W1: 604800,
    EnumTimeframe.MO1: 2592000,
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
