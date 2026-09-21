import logging
import time
from datetime import date
from typing import Callable

from app.models.filtro import Filtro
from app.scanner.buffered_candle import BufferedCandle
from app.scanner.day_summary import DaySummary, apply_bar
from app.scanner.session_clock import today_et
from app.scanner.timeframe import necesita_resumen_del_dia, usa_perfil_de_volumen
from app.scanner.volume_profile import VolumeProfile

logger = logging.getLogger(__name__)

ProfileLoader = Callable[[list[str], str], dict[str, VolumeProfile]]

_RETRY_MISSING_SECONDS = 900
_RETRY_ERROR_SECONDS = 60


class SessionState:
    """Resumen de la sesion (primera vela, maximo, minimo, volumen
    acumulado) y perfil de volumen por (simbolo, timeframe) para los grupos
    cuyos filtros lo necesitan -- reemplaza guardar cientos de velas solo
    para sacar esos numeros."""

    def __init__(self, profile_loader: ProfileLoader | None = None):
        self._loader = profile_loader
        self._days: dict[tuple[str, str], DaySummary] = {}
        self._profiles: dict[tuple[str, str], VolumeProfile] = {}
        self._retry_at: dict[str, float] = {}
        self._date: date | None = None
        self._day_timeframes: set[str] = set()
        self._profile_timeframes: set[str] = set()

    def configurar(self, grupos: list[tuple[int, str, list[Filtro]]]) -> None:
        self._day_timeframes = {label for _, label, filtros in grupos if necesita_resumen_del_dia(filtros)}
        self._profile_timeframes = {label for _, label, filtros in grupos if usa_perfil_de_volumen(filtros)}

    def sembrar(self, symbol: str, timeframe: str, candles: list[BufferedCandle]) -> None:
        if timeframe not in self._day_timeframes:
            return
        summary = None
        for candle in candles:
            summary = apply_bar(summary, candle)
        if summary is None:
            self._days.pop((symbol, timeframe), None)
        else:
            self._days[(symbol, timeframe)] = summary

    def actualizar(self, symbol: str, timeframe: str, candle: BufferedCandle) -> None:
        if timeframe not in self._day_timeframes:
            return
        summary = apply_bar(self._days.get((symbol, timeframe)), candle)
        if summary is not None:
            self._days[(symbol, timeframe)] = summary

    def day(self, symbol: str, timeframe: str) -> DaySummary | None:
        return self._days.get((symbol, timeframe))

    def profile(self, symbol: str, timeframe: str) -> VolumeProfile | None:
        return self._profiles.get((symbol, timeframe))

    def olvidar(self, keys: set[tuple[str, str]]) -> None:
        for key in keys:
            self._days.pop(key, None)

    def podar(self, keys: set[tuple[str, str]]) -> None:
        for key in [k for k in self._days if k not in keys]:
            del self._days[key]

    def cargar_perfiles(self, universo: set[str]) -> None:
        if self._loader is None or not self._profile_timeframes:
            return
        hoy = today_et()
        if hoy != self._date:
            self._profiles.clear()
            self._retry_at.clear()
            self._date = hoy
        for timeframe in self._profile_timeframes:
            faltan = [s for s in universo if (s, timeframe) not in self._profiles]
            if not faltan or time.monotonic() < self._retry_at.get(timeframe, 0.0):
                continue
            try:
                cargados = self._loader(faltan, timeframe)
            except Exception as e:
                logger.warning("SessionState: no se pudo cargar el perfil de volumen %s: %s", timeframe, e)
                self._retry_at[timeframe] = time.monotonic() + _RETRY_ERROR_SECONDS
                continue
            for symbol, profile in cargados.items():
                self._profiles[(symbol, timeframe)] = profile
            sin_perfil = any(s not in cargados for s in faltan)
            self._retry_at[timeframe] = time.monotonic() + (_RETRY_MISSING_SECONDS if sin_perfil else 0.0)
