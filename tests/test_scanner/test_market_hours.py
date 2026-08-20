from datetime import date, time

from app.scanner.calendar import effective_end, market_close_time


def test_regular_close_time():
    assert market_close_time(date(2026, 7, 16)) == time(20, 0, 0)


def test_early_close_july_3():
    assert market_close_time(date(2026, 7, 3)) == time(17, 0, 0)


def test_early_close_nov_27():
    assert market_close_time(date(2026, 11, 27)) == time(17, 0, 0)


def test_effective_end_respects_scanner_hora_fin():
    result = effective_end(time(12, 0, 0), date(2026, 7, 16))
    assert result == time(12, 0, 0)


def test_effective_end_allows_extended_hours():
    result = effective_end(time(23, 0, 0), date(2026, 7, 16))
    assert result == time(23, 0, 0)


def test_effective_end_caps_at_early_close():
    result = effective_end(time(20, 0, 0), date(2026, 7, 3))
    assert result == time(17, 0, 0)


def test_effective_end_respects_earlier_hora_fin_on_early_close_day():
    result = effective_end(time(14, 0, 0), date(2026, 7, 3))
    assert result == time(14, 0, 0)
