import logging
from datetime import date, datetime, time, timedelta
from typing import List

logger = logging.getLogger(__name__)

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

_EARLY_CLOSE_TIME = time(17, 0, 0)


_REGULAR_CLOSE = time(20, 0, 0)

# Apertura real del pre-market extendido (dxFeed/TastyTrade) -- fuera de
# [_MARKET_OPEN_TIME, market_close_time()] no hay actividad real (ni
# trades, ni velas nuevas), asi que un escaner configurado con horaInicio
# antes de esto solo evaluaria datos muertos hasta que el mercado abra de
# verdad. No cambia por dia (a diferencia del cierre, no hay apertura
# "anticipada" en el calendario US).
_MARKET_OPEN_TIME = time(4, 0, 0)


def market_close_time(check_date: date) -> time:
    if check_date in _EARLY_CLOSE_DATES:
        return _EARLY_CLOSE_TIME
    return _REGULAR_CLOSE


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


def effective_start(escaner_start: time) -> time:
    # Simetrico a effective_end: un escaner configurado fuera de
    # [_MARKET_OPEN_TIME, _REGULAR_CLOSE) queda recortado a la apertura de
    # pre-market -- evaluar horas de mercado genuinamente muerto no puede
    # producir ninguna señal real, solo carga inutil sobre
    # marketdata-service. max() por si solo NO alcanza aca: 21:00 (noche
    # muerta) es numericamente MAYOR que las 04:00 de apertura, asi que
    # max(21:00, 04:00) devolveria 21:00 sin recortar nada -- hay que
    # chequear el rango explicito, no comparar como si el dia no diera la
    # vuelta. Un horaInicio YA dentro de horas reales (ej. 9:30) no se toca.
    if _MARKET_OPEN_TIME <= escaner_start < _REGULAR_CLOSE:
        return escaner_start
    return _MARKET_OPEN_TIME


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
