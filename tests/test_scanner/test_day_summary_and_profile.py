from array import array
from datetime import datetime, timezone

from app.scanner.buffered_candle import BufferedCandle
from app.scanner.day_summary import apply_bar
from app.scanner.session_clock import SESSION_SLOTS, session_slot
from app.scanner.volume_profile import VolumeProfile, profile_from_response


def _bar(ts: datetime, high=2.0, low=1.0, volume=10.0) -> BufferedCandle:
    return BufferedCandle(symbol="AAPL", timestamp=ts, open=1.5, high=high, low=low, close=1.5, volume=volume)


def test_apertura_del_premercado_es_el_slot_cero_en_verano_e_invierno():
    assert session_slot(datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc))[1] == 0
    assert session_slot(datetime(2026, 12, 15, 9, 0, tzinfo=timezone.utc))[1] == 0


def test_el_postmercado_tardio_de_invierno_sigue_en_la_misma_sesion():
    antes = session_slot(datetime(2026, 12, 15, 23, 30, tzinfo=timezone.utc))
    ultimo = session_slot(datetime(2026, 12, 16, 0, 59, tzinfo=timezone.utc))

    assert ultimo[1] == SESSION_SLOTS - 1
    assert ultimo[0] == antes[0]


def test_fuera_de_la_sesion_extendida_no_hay_slot():
    assert session_slot(datetime(2026, 9, 18, 7, 59, tzinfo=timezone.utc)) is None
    assert session_slot(datetime(2026, 9, 19, 0, 0, tzinfo=timezone.utc)) is None


def test_el_resumen_acumula_maximo_minimo_y_volumen_del_dia():
    t0 = datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc)
    resumen = apply_bar(None, _bar(t0, high=5, low=3, volume=100))
    resumen = apply_bar(resumen, _bar(datetime(2026, 9, 18, 13, 31, tzinfo=timezone.utc), high=9, low=4, volume=50))
    resumen = apply_bar(resumen, _bar(datetime(2026, 9, 18, 13, 32, tzinfo=timezone.utc), high=6, low=1, volume=25))

    assert (resumen.high, resumen.low, resumen.volume) == (9, 1, 175)
    assert resumen.first.timestamp == t0


def test_una_sesion_nueva_reinicia_el_resumen():
    viejo = apply_bar(None, _bar(datetime(2026, 9, 17, 13, 30, tzinfo=timezone.utc), high=99, volume=1000))
    nuevo = apply_bar(viejo, _bar(datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc), high=5, volume=10))

    assert (nuevo.high, nuevo.volume) == (5, 10)


def test_una_vela_fuera_de_sesion_no_cambia_el_resumen():
    resumen = apply_bar(None, _bar(datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc), volume=10))

    igual = apply_bar(resumen, _bar(datetime(2026, 9, 18, 7, 0, tzinfo=timezone.utc), volume=999))

    assert igual is resumen and igual.volume == 10


def test_el_perfil_devuelve_el_acumulado_esperado_de_la_franja_de_la_vela():
    perfil = profile_from_response({"slotMinutes": 5, "sessions": 20, "cumulative": list(range(100, 100 + 192))})

    esperado = perfil.expected_through(datetime(2026, 9, 18, 8, 5, tzinfo=timezone.utc))

    assert esperado == 101


def test_el_perfil_sin_franja_para_esa_hora_devuelve_none():
    perfil = VolumeProfile(slot_minutes=5, cumulative=array("f", [1.0, 2.0]))

    assert perfil.expected_through(datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc)) is None
    assert perfil.expected_through(datetime(2026, 9, 18, 7, 0, tzinfo=timezone.utc)) is None
