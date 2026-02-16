"""Validador de barras: verifica que las velas recibidas sean correctas."""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from domain.models.candle import Candle
from config import VALIDACION_TOLERANCIA_SEGUNDOS

logger = logging.getLogger(__name__)

INTERVALO_POR_TIMEFRAME = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "D1": 86400, "W1": 604800, "MO1": 2592000,
}

NYSE_TZ = ZoneInfo("America/New_York")
HORA_CIERRE_NYSE = 16  # 4:00 PM ET


@dataclass
class ResultadoValidacion:
    valido: bool
    razon: str = ""


def validar_barras(
    candles: list[Candle],
    timeframe: str,
    ahora: Optional[datetime] = None,
) -> ResultadoValidacion:
    """Valida que las barras recibidas sean correctas.

    Verificaciones:
    1. Lista no vacia
    2. Timestamp de ultima barra corresponde al periodo esperado
    3. Datos OHLCV validos (no NaN, no todos cero)
    """
    if not candles:
        return ResultadoValidacion(False, "Lista de candles vacia")

    ahora = ahora or datetime.now(timezone.utc)

    # Validar datos OHLCV de la ultima barra
    resultado_datos = _validar_datos_ohlcv(candles[-1])
    if not resultado_datos.valido:
        return resultado_datos

    # Validar timestamp de la ultima barra
    resultado_timestamp = _validar_timestamp_ultima_barra(candles, timeframe, ahora)
    if not resultado_timestamp.valido:
        return resultado_timestamp

    return ResultadoValidacion(True)


def _validar_datos_ohlcv(candle: Candle) -> ResultadoValidacion:
    """Verifica que los datos OHLCV no sean NaN ni todos cero."""
    valores = [candle.open, candle.high, candle.low, candle.close]

    for nombre, valor in [("open", candle.open), ("high", candle.high),
                           ("low", candle.low), ("close", candle.close),
                           ("volume", candle.volume)]:
        if math.isnan(valor) or math.isinf(valor):
            return ResultadoValidacion(False, f"Valor {nombre} invalido: {valor}")

    if all(v == 0 for v in valores):
        return ResultadoValidacion(False, "Todos los valores OHLC son 0")

    return ResultadoValidacion(True)


def _validar_timestamp_ultima_barra(
    candles: list[Candle],
    timeframe: str,
    ahora: datetime,
) -> ResultadoValidacion:
    """Verifica que la ultima barra corresponda al periodo esperado."""
    intervalo = INTERVALO_POR_TIMEFRAME.get(timeframe)
    if intervalo is None:
        return ResultadoValidacion(True, f"Timeframe {timeframe} no validable")

    ultima = candles[-1]
    ts_ultima = ultima.get_datetime()
    if ts_ultima is None:
        return ResultadoValidacion(False, f"Timestamp no parseable: {ultima.timestamp}")

    ts_esperado = _calcular_timestamp_ultima_barra_cerrada(ahora, timeframe, intervalo)
    if ts_esperado is None:
        return ResultadoValidacion(True, "No se puede validar fuera de horario")

    diferencia = abs((ts_ultima - ts_esperado).total_seconds())

    if diferencia <= VALIDACION_TOLERANCIA_SEGUNDOS:
        return ResultadoValidacion(True)

    return ResultadoValidacion(
        False,
        f"Barra desactualizada: esperada={ts_esperado.isoformat()}, "
        f"recibida={ts_ultima.isoformat()}, diferencia={diferencia:.0f}s"
    )


def _calcular_timestamp_ultima_barra_cerrada(
    ahora: datetime,
    timeframe: str,
    intervalo_segundos: int,
) -> Optional[datetime]:
    """Calcula el timestamp de inicio de la ultima barra que deberia estar cerrada.

    Para intraday (M1-H1): alinea al epoch y resta un periodo.
    Para D1: la ultima barra cerrada es el dia de trading anterior.
    """
    if timeframe == "D1":
        return _calcular_ultima_barra_d1(ahora)

    if timeframe in ("W1", "MO1"):
        # Timeframes semanales/mensuales: no validar timestamp exacto
        return None

    # Intraday: alinear al epoch
    epoch_seg = int(ahora.timestamp())
    seg_en_barra = epoch_seg % intervalo_segundos
    inicio_barra_actual = ahora - timedelta(seconds=seg_en_barra)

    # La ultima barra CERRADA es la anterior a la actual
    inicio_ultima_cerrada = inicio_barra_actual - timedelta(seconds=intervalo_segundos)

    return inicio_ultima_cerrada


def _calcular_ultima_barra_d1(ahora: datetime) -> Optional[datetime]:
    """Calcula el timestamp de la ultima barra diaria cerrada.

    Usa zoneinfo para manejar DST correctamente.
    """
    ahora_ny = ahora.astimezone(NYSE_TZ)

    if ahora_ny.hour >= HORA_CIERRE_NYSE:
        # Despues del cierre: la barra de hoy deberia estar cerrada
        dia_barra = ahora_ny.date()
    else:
        # Antes del cierre: la ultima cerrada es la de ayer
        dia_barra = (ahora_ny - timedelta(days=1)).date()

    # Retroceder si cae en fin de semana
    while dia_barra.weekday() >= 5:  # sabado=5, domingo=6
        dia_barra = dia_barra - timedelta(days=1)

    # Retornar como UTC midnight del dia de la barra
    return datetime(dia_barra.year, dia_barra.month, dia_barra.day,
                    tzinfo=timezone.utc)
