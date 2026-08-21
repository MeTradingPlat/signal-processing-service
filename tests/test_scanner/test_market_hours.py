from datetime import date, time

from app.scanner.calendar import effective_end, effective_start, market_close_time

_EDT_DATE = date(2026, 7, 16)   # ET = UTC-4
_EST_DATE = date(2026, 12, 10)  # ET = UTC-5
_EARLY_CLOSE_EDT_DATE = date(2026, 7, 3)
_EARLY_CLOSE_EST_DATE = date(2026, 11, 27)


def test_regular_close_time_edt():
    assert market_close_time(_EDT_DATE) == time(0, 0, 0)


def test_regular_close_time_est():
    assert market_close_time(_EST_DATE) == time(1, 0, 0)


def test_early_close_july_3():
    assert market_close_time(_EARLY_CLOSE_EDT_DATE) == time(21, 0, 0)


def test_early_close_nov_27():
    assert market_close_time(_EARLY_CLOSE_EST_DATE) == time(22, 0, 0)


def test_effective_end_respects_scanner_hora_fin():
    result = effective_end(time(12, 0, 0), _EDT_DATE)
    assert result == time(12, 0, 0)


def test_effective_end_allows_extended_hours():
    result = effective_end(time(23, 0, 0), _EDT_DATE)
    assert result == time(23, 0, 0)


def test_effective_end_caps_at_early_close():
    result = effective_end(time(23, 0, 0), _EARLY_CLOSE_EDT_DATE)
    assert result == time(21, 0, 0)


def test_effective_end_respects_earlier_hora_fin_on_early_close_day():
    result = effective_end(time(14, 0, 0), _EARLY_CLOSE_EDT_DATE)
    assert result == time(14, 0, 0)


def test_effective_start_respects_post_market_hora_inicio():
    # Regression: un horaInicio de post-market (16:00 ET = 20:00 UTC en EDT)
    # se estaba recortando a las 04:00 UTC por comparar el rango 4am-8pm ET
    # directo contra un horaInicio que ya viene en UTC -- el bug real que
    # dejaba un escaner de post-market corriendo casi 24 horas en vez de
    # solo su ventana.
    result = effective_start(time(20, 0, 0), _EDT_DATE)
    assert result == time(20, 0, 0)


def test_effective_start_respects_regular_hora_inicio():
    result = effective_start(time(13, 30, 0), _EDT_DATE)
    assert result == time(13, 30, 0)


def test_effective_start_respects_pre_market_hora_inicio():
    result = effective_start(time(9, 30, 0), _EDT_DATE)
    assert result == time(9, 30, 0)


def test_effective_start_caps_dead_late_night_hours_edt():
    result = effective_start(time(3, 0, 0), _EDT_DATE)
    assert result == time(8, 0, 0)


def test_effective_start_caps_dead_early_morning_hours_edt():
    result = effective_start(time(7, 0, 0), _EDT_DATE)
    assert result == time(8, 0, 0)


def test_effective_start_shifts_with_dst_est():
    # En EST (UTC-5) la apertura de pre-market (4am ET) cae una hora mas
    # tarde en UTC que en EDT -- confirma que la conversion usa el offset
    # real del dia (zoneinfo), no uno fijo.
    assert effective_start(time(9, 0, 0), _EST_DATE) == time(9, 0, 0)
    assert effective_start(time(8, 0, 0), _EST_DATE) == time(9, 0, 0)
    assert effective_start(time(1, 0, 0), _EST_DATE) == time(1, 0, 0)
    assert effective_start(time(2, 0, 0), _EST_DATE) == time(9, 0, 0)
