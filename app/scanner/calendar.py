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

_EARLY_CLOSE_TIME = time(13, 0, 0)


_REGULAR_CLOSE = time(16, 0, 0)


def market_close_time(check_date: date) -> time:
    if check_date in _EARLY_CLOSE_DATES:
        return _EARLY_CLOSE_TIME
    return _REGULAR_CLOSE


def effective_end(escaner_end: time, _check_date: date) -> time:
    return escaner_end


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
