import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import List
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

_US_HOLIDAYS_2026: List[date] = [
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
]

_EARLY_CLOSE_DATES: set[date] = {
    date(2026, 7, 3),
    date(2026, 11, 27),
    date(2026, 12, 24),
}

_EARLY_CLOSE_TIME_ET = time(17, 0, 0)


_REGULAR_CLOSE_ET = time(20, 0, 0)

# Apertura real del pre-market extendido (dxFeed/TastyTrade) -- fuera de
# [_MARKET_OPEN_TIME_ET, market_close_time()] no hay actividad real (ni
# trades, ni velas nuevas), asi que un escaner configurado con horaInicio
# antes de esto solo evaluaria datos muertos hasta que el mercado abra de
# verdad. No cambia por dia (a diferencia del cierre, no hay apertura
# "anticipada" en el calendario US).
_MARKET_OPEN_TIME_ET = time(4, 0, 0)


def _et_to_utc_time(et_time: time, check_date: date) -> time:
    """Convierte una hora de pared ET a su equivalente UTC para una fecha
    dada. escaner.horaInicio/horaFin llegan siempre en UTC (confirmado
    contra la BD: un escaner de post-market guarda hora_inicio=20:00:00) --
    comparar directo contra constantes en ET (como se hacia antes) rompia
    cualquier escaner cuyo horaInicio cayera en la tarde/noche UTC (que es
    justo donde vive TODO el rango 4am-8pm ET, por el offset de EE.UU.).
    Un offset fijo (+4/+5) tambien rompe en el cambio de horario de verano
    -- zoneinfo usa el offset real de ese dia."""
    return datetime.combine(check_date, et_time, tzinfo=_ET).astimezone(timezone.utc).time()


def market_close_time(check_date: date) -> time:
    et_close = _EARLY_CLOSE_TIME_ET if check_date in _EARLY_CLOSE_DATES else _REGULAR_CLOSE_ET
    return _et_to_utc_time(et_close, check_date)


def effective_end(escaner_end: time, check_date: date) -> time:
    # market_close_time() esta implementada y probada pero nadie la llamaba
    # -- en un dia de _EARLY_CLOSE_DATES, un escaner configurado hasta el
    # cierre extendido normal (ej. 20:00, o cualquier hora que el usuario
    # elija -- un dia normal se respeta tal cual, horas extendidas
    # incluidas) seguia evaluando horas despues del cierre real (17:00),
    # contra un mercado que ya no imprime velas nuevas. Solo se recorta en
    # los dias especiales; min() tambien respeta un horaFin mas TEMPRANO
    # que el cierre anticipado (alguien que solo quiere escanear hasta las
    # 14:00 no debe extenderse a las 17:00).
    if check_date not in _EARLY_CLOSE_DATES:
        return escaner_end
    return min(escaner_end, market_close_time(check_date))


def effective_start(escaner_start: time, check_date: date) -> time:
    # Simetrico a effective_end: un escaner configurado fuera de las horas
    # reales de mercado (4am-8pm ET, convertido a UTC para check_date) queda
    # recortado a la apertura de pre-market -- evaluar horas de mercado
    # genuinamente muerto no puede producir ninguna señal real, solo carga
    # inutil sobre marketdata-service. El rango 4am-8pm ET SIEMPRE cruza
    # medianoche UTC (ET va detras de UTC todo el año), asi que "dentro de
    # rango" es "hora >= apertura O hora <= cierre", nunca un simple <=
    # entre los dos valores. Un horaInicio YA dentro de horas reales (ej.
    # 9:30 ET / 13:30 UTC, o 16:00 ET / 20:00 UTC de post-market) no se toca.
    open_utc = _et_to_utc_time(_MARKET_OPEN_TIME_ET, check_date)
    close_utc = _et_to_utc_time(_REGULAR_CLOSE_ET, check_date)
    if escaner_start >= open_utc or escaner_start <= close_utc:
        return escaner_start
    return open_utc


def is_trading_day(check_date: date) -> bool:
    if check_date.weekday() >= 5:
        return False
    if check_date in _US_HOLIDAYS_2026:
        return False
    return True


def next_trading_day(from_date: date) -> date:
    candidate = from_date + timedelta(days=1)
    while not is_trading_day(candidate):
        candidate = candidate + timedelta(days=1)
    return candidate


def next_trading_window(start_time: time, from_datetime: datetime) -> datetime:
    target_date = from_datetime.date()
    window_start = datetime.combine(target_date, start_time, tzinfo=from_datetime.tzinfo)
    if window_start > from_datetime and is_trading_day(target_date):
        return window_start
    next_day = next_trading_day(target_date)
    return datetime.combine(next_day, start_time, tzinfo=from_datetime.tzinfo)


def is_within_window(now: datetime, start: time, end: time) -> bool:
    if start <= end:
        return is_trading_day(now.date()) and start <= now.time() <= end
    if now.time() >= start:
        return is_trading_day(now.date())
    if now.time() <= end:
        yesterday = now.date() - timedelta(days=1)
        return is_trading_day(yesterday) and is_trading_day(now.date())
    return False
