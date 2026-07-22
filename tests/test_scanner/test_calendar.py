from datetime import date, datetime, time

from app.scanner.calendar import is_trading_day, is_within_window, next_trading_day, next_trading_window


def test_weekday_is_trading_day():
    assert is_trading_day(date(2026, 7, 14))


def test_saturday_is_not_trading_day():
    assert not is_trading_day(date(2026, 7, 18))


def test_sunday_is_not_trading_day():
    assert not is_trading_day(date(2026, 7, 19))


def test_christmas_is_not_trading_day():
    assert not is_trading_day(date(2026, 12, 25))


def test_next_trading_day_from_friday():
    assert next_trading_day(date(2026, 7, 17)) == date(2026, 7, 20)


def test_next_trading_day_from_saturday():
    assert next_trading_day(date(2026, 7, 18)) == date(2026, 7, 20)


def test_is_within_window():
    now = datetime(2026, 7, 17, 10, 30, 0)
    assert is_within_window(now, time(9, 30), time(16, 0))


def test_is_outside_window_early():
    now = datetime(2026, 7, 17, 5, 0, 0)
    assert not is_within_window(now, time(9, 30), time(16, 0))


def test_is_outside_window_weekend():
    now = datetime(2026, 7, 18, 10, 30, 0)
    assert not is_within_window(now, time(9, 30), time(16, 0))


def test_next_trading_window_same_day():
    now = datetime(2026, 7, 17, 5, 0, 0)
    target = next_trading_window(time(9, 30), now)
    assert target == datetime(2026, 7, 17, 9, 30)


def test_next_trading_window_already_passed():
    now = datetime(2026, 7, 17, 17, 0, 0)
    target = next_trading_window(time(9, 30), now)
    assert target == datetime(2026, 7, 20, 9, 30)
