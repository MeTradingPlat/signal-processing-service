"""GestorTiempo — manejo de tiempo robusto para EjecutorEscaner.

Responsabilidades:
  - Detectar días hábiles (festivos + fines de semana) por mercado
  - Calcular el siguiente día hábil para escaneres DIARIA
  - Dormir hasta un objetivo con polling anti-drift (NTP, jitter, suspend)
  - Calcular espera hasta el próximo cierre de vela alineado al timeframe
"""

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Categorías de mercados
# ---------------------------------------------------------------------------

# Mercados que operan 24/7 — nunca tienen festivos ni fines de semana
_MERCADOS_CONTINUO: frozenset[str] = frozenset({"CRYPTO", "FOREX"})

# Mercados que siguen el calendario NYSE / NASDAQ
_MERCADOS_NYSE: frozenset[str] = frozenset({"NYSE", "NASDAQ", "AMEX", "OTC", "US_EQUITY"})


# ---------------------------------------------------------------------------
# Cálculo de festivos NYSE
# ---------------------------------------------------------------------------

def _pascua(year: int) -> date:
    """Domingo de Pascua — algoritmo gregoriano anónimo."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _viernes_santo(year: int) -> date:
    return _pascua(year) - timedelta(days=2)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-ésimo día de la semana en un mes (n=1 es el primero).

    weekday: 0=lunes … 6=domingo
    """
    d = date(year, month, 1)
    diff = (weekday - d.weekday()) % 7
    d += timedelta(days=diff)
    d += timedelta(weeks=n - 1)
    return d


def _ultimo_weekday(year: int, month: int, weekday: int) -> date:
    """Último día de la semana en un mes."""
    ultimo_dia = (
        date(year + 1, 1, 1) - timedelta(days=1)
        if month == 12
        else date(year, month + 1, 1) - timedelta(days=1)
    )
    diff = (ultimo_dia.weekday() - weekday) % 7
    return ultimo_dia - timedelta(days=diff)


def _observado(d: date) -> date:
    """Ajusta un festivo caído en fin de semana al día hábil más cercano."""
    if d.weekday() == 5:   # sábado → viernes anterior
        return d - timedelta(days=1)
    if d.weekday() == 6:   # domingo → lunes siguiente
        return d + timedelta(days=1)
    return d


def festivos_nyse(year: int) -> frozenset[date]:
    """Retorna el conjunto de días festivos del NYSE para el año dado."""
    h: set[date] = set()

    # New Year's Day
    h.add(_observado(date(year, 1, 1)))

    # MLK Day — 3er lunes de enero
    h.add(_nth_weekday(year, 1, 0, 3))

    # Presidents Day — 3er lunes de febrero
    h.add(_nth_weekday(year, 2, 0, 3))

    # Good Friday
    h.add(_viernes_santo(year))

    # Memorial Day — último lunes de mayo
    h.add(_ultimo_weekday(year, 5, 0))

    # Juneteenth (desde 2022)
    if year >= 2022:
        h.add(_observado(date(year, 6, 19)))

    # Independence Day
    h.add(_observado(date(year, 7, 4)))

    # Labor Day — 1er lunes de septiembre
    h.add(_nth_weekday(year, 9, 0, 1))

    # Thanksgiving — 4° jueves de noviembre
    h.add(_nth_weekday(year, 11, 3, 4))

    # Christmas
    h.add(_observado(date(year, 12, 25)))

    return frozenset(h)


# ---------------------------------------------------------------------------
# GestorTiempo
# ---------------------------------------------------------------------------

class GestorTiempo:
    """Centraliza el manejo de tiempo para los ejecutores de escaneres.

    El método ``ahora_utc`` está separado para facilitar el reemplazo en tests
    sin parchear el módulo ``datetime``.
    """

    def __init__(self, poll_seg: int = 60) -> None:
        self._poll = poll_seg
        self._cache_festivos: dict[tuple[str, int], frozenset[date]] = {}

    # ------------------------------------------------------------------
    # Reloj centralizado — reemplazable en tests
    # ------------------------------------------------------------------

    def ahora_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Días hábiles
    # ------------------------------------------------------------------

    def _festivos(self, mercado: str, year: int) -> frozenset[date]:
        key = (mercado.upper(), year)
        if key not in self._cache_festivos:
            m = mercado.upper()
            if m in _MERCADOS_CONTINUO:
                self._cache_festivos[key] = frozenset()
            else:
                self._cache_festivos[key] = festivos_nyse(year)
        return self._cache_festivos[key]

    def es_dia_habil(self, mercado: str, fecha: date | None = None) -> bool:
        """True si el mercado opera en ``fecha`` (default: hoy UTC)."""
        if fecha is None:
            fecha = self.ahora_utc().date()

        m = mercado.upper()

        # Mercados continuos nunca cierran
        if m in _MERCADOS_CONTINUO:
            return True

        # Fin de semana
        if fecha.weekday() >= 5:
            return False

        return fecha not in self._festivos(m, fecha.year)

    def siguiente_dia_habil(
        self,
        mercados: list[str],
        desde: date | None = None,
    ) -> date:
        """Próximo día en que TODOS los mercados estén abiertos.

        Busca a partir de ``desde + 1 día`` (no incluye ``desde``).
        """
        if desde is None:
            desde = self.ahora_utc().date()

        candidato = desde + timedelta(days=1)
        for _ in range(30):
            if all(self.es_dia_habil(m, candidato) for m in mercados):
                return candidato
            candidato += timedelta(days=1)

        raise RuntimeError(
            f"No se encontró día hábil en 30 días para mercados {mercados}"
        )

    # ------------------------------------------------------------------
    # Sleep anti-drift
    # ------------------------------------------------------------------

    async def dormir_hasta(
        self,
        objetivo: datetime,
        poll: int | None = None,
    ) -> None:
        """Duerme hasta ``objetivo`` re-evaluando el reloj real cada ``poll`` segundos.

        Si el proceso despierta antes (jitter del OS, NTP, suspend) el método
        vuelve a calcular el tiempo restante y duerme de nuevo, garantizando
        que nunca se avanza antes de que el reloj supere ``objetivo``.
        """
        poll = poll if poll is not None else self._poll
        while True:
            ahora = self.ahora_utc()
            restante = (objetivo - ahora).total_seconds()
            if restante <= 0:
                return
            intervalo = min(poll, restante)
            logger.debug(
                "dormir_hasta: faltan %.1fs, próximo tick en %.1fs",
                restante,
                intervalo,
            )
            await asyncio.sleep(intervalo)

    async def dormir_hasta_hora(
        self,
        hora_objetivo: time,
        fecha_base: datetime | None = None,
        poll: int | None = None,
    ) -> None:
        """Duerme hasta que el reloj UTC alcance ``hora_objetivo``.

        Si la hora ya pasó en la fecha base, espera al día siguiente.
        """
        ahora = fecha_base or self.ahora_utc()
        objetivo = ahora.replace(
            hour=hora_objetivo.hour,
            minute=hora_objetivo.minute,
            second=hora_objetivo.second,
            microsecond=0,
        )
        if objetivo <= ahora:
            objetivo += timedelta(days=1)
        await self.dormir_hasta(objetivo, poll=poll)

    # ------------------------------------------------------------------
    # Espera de vela alineada al timeframe
    # ------------------------------------------------------------------

    def calcular_espera_vela(
        self,
        intervalo_seg: int,
        margen_seg: int = 2,
    ) -> float:
        """Segundos hasta el próximo cierre de vela alineado al timeframe.

        ``margen_seg`` es un pequeño margen para asegurar que la vela ya
        cerró en el servidor de marketdata antes de consultarla.
        """
        ahora_ts = self.ahora_utc().timestamp()
        siguiente_ts = ((int(ahora_ts) // intervalo_seg) + 1) * intervalo_seg
        return (siguiente_ts - ahora_ts) + margen_seg

    # ------------------------------------------------------------------
    # Helper: construir datetime UTC para hora + fecha
    # ------------------------------------------------------------------

    def construir_datetime_utc(
        self,
        hora: time,
        fecha: date | None = None,
    ) -> datetime:
        """Construye un datetime UTC para ``hora`` en ``fecha`` (default: hoy)."""
        if fecha is None:
            fecha = self.ahora_utc().date()
        return datetime(
            fecha.year, fecha.month, fecha.day,
            hora.hour, hora.minute, hora.second,
            tzinfo=timezone.utc,
        )
