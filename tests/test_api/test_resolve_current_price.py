from app.api.routes_pivots import _resolve_current_price


def test_signal_reference_uses_explicit_price_directly():
    assert _resolve_current_price("AAPL", "signal", 123.45) == 123.45


def test_signal_reference_without_explicit_price_returns_none():
    # Una senal sin precio (hay senales que no lo tienen) no debe intentar
    # resolver nada del mercado -- el frontend ya filtra esta opcion para
    # esos casos, pero el backend no debe asumirlo.
    assert _resolve_current_price("AAPL", "signal", None) is None
