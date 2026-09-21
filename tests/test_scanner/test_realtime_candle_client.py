from app.scanner.realtime_candle_client import _group_by_timeframe


def test_group_by_timeframe_agrupa_simbolos_del_mismo_timeframe():
    keys = {("AAPL", "M5"), ("MSFT", "M5"), ("AAPL", "D1")}

    grouped = _group_by_timeframe(keys)

    assert grouped.keys() == {"M5", "D1"}
    assert sorted(grouped["M5"]) == ["AAPL", "MSFT"]
    assert grouped["D1"] == ["AAPL"]


def test_group_by_timeframe_set_vacio_da_dict_vacio():
    assert _group_by_timeframe(set()) == {}


def test_frames_de_suscripcion_incluyen_las_barras_de_cada_timeframe():
    from app.scanner.realtime_candle_client import _frames

    frames = _frames("subscribe", {("AAPL", "M1"), ("AAPL", "D1")}, lambda tf: {"M1": 151, "D1": 60}[tf])

    assert {f["timeframe"]: f["bars"] for f in frames} == {"M1": 151, "D1": 60}


def test_frames_de_suscripcion_piden_solo_velas_cerradas():
    from app.scanner.realtime_candle_client import _frames

    con_barras = _frames("subscribe", {("AAPL", "M1")}, lambda tf: 151)[0]
    sin_barras = _frames("subscribe", {("AAPL", "M1")}, None)[0]

    assert con_barras["closedOnly"] is True and sin_barras["closedOnly"] is True


def test_frames_de_desuscripcion_no_llevan_barras():
    from app.scanner.realtime_candle_client import _frames

    frames = _frames("unsubscribe", {("AAPL", "M1")}, lambda tf: 151)

    assert "bars" not in frames[0] and "closedOnly" not in frames[0]


def test_frames_sin_funcion_de_barras_no_llevan_el_campo():
    from app.scanner.realtime_candle_client import _frames

    assert "bars" not in _frames("subscribe", {("AAPL", "M1")}, None)[0]
