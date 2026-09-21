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


def _cliente_de_prueba():
    import json

    from app.scanner.realtime_candle_client import RealtimeCandleClient

    class _Ws:
        def __init__(self):
            self.enviados = []

        def send(self, raw):
            self.enviados.append(json.loads(raw))

    cliente = RealtimeCandleClient.__new__(RealtimeCandleClient)
    cliente._ws = _Ws()
    cliente._bars_for = lambda tf: 151
    cliente._last_seq = {}
    cliente.historiales, cliente.barras = [], []
    cliente._on_history = lambda s, tf, bars: cliente.historiales.append((s, tf))
    cliente._on_bar = lambda s, tf, bar: cliente.barras.append(bar["seq"] if "seq" in bar else bar["time"])
    return cliente


def _mensaje(seq=None, corrected=False, time=1):
    import json

    bar = {"time": time, "closed": True}
    if seq is not None:
        bar["seq"] = seq
    if corrected:
        bar["corrected"] = True
    return json.dumps({"type": "bar", "symbol": "AAPL", "timeframe": "M1", "bar": bar})


def _historial():
    import json

    return json.dumps({"type": "history", "symbol": "AAPL", "timeframe": "M1", "bars": []})


def test_velas_con_secuencia_consecutiva_se_entregan_sin_resincronizar():
    cliente = _cliente_de_prueba()
    cliente._on_message(_historial())

    for seq in (1, 2, 3):
        cliente._on_message(_mensaje(seq))

    assert cliente.barras == [1, 2, 3]
    assert cliente._ws.enviados == []


def test_un_salto_de_secuencia_pide_el_historial_de_esa_serie_y_descarta_la_vela():
    cliente = _cliente_de_prueba()
    cliente._on_message(_historial())
    cliente._on_message(_mensaje(1))

    cliente._on_message(_mensaje(3))

    assert cliente.barras == [1]
    assert cliente._ws.enviados[0] == {"action": "unsubscribe", "symbols": ["AAPL"], "timeframe": "M1"}
    assert cliente._ws.enviados[1] == {"action": "subscribe", "symbols": ["AAPL"], "timeframe": "M1",
                                       "closedOnly": True, "bars": 151}


def test_tras_el_historial_nuevo_la_secuencia_vuelve_a_empezar_en_uno():
    cliente = _cliente_de_prueba()
    cliente._on_message(_historial())
    cliente._on_message(_mensaje(1))
    cliente._on_message(_mensaje(3))

    cliente._on_message(_historial())
    cliente._on_message(_mensaje(1))

    assert cliente.barras == [1, 1]
    assert len(cliente._ws.enviados) == 2


def test_las_velas_corregidas_no_afectan_la_secuencia():
    cliente = _cliente_de_prueba()
    cliente._on_message(_historial())
    cliente._on_message(_mensaje(1))

    cliente._on_message(_mensaje(corrected=True, time=99))
    cliente._on_message(_mensaje(2))

    assert cliente.barras == [1, 99, 2]
    assert cliente._ws.enviados == []


def test_una_secuencia_repetida_o_anterior_se_descarta_sin_resincronizar():
    cliente = _cliente_de_prueba()
    cliente._on_message(_historial())
    cliente._on_message(_mensaje(1))
    cliente._on_message(_mensaje(2))

    cliente._on_message(_mensaje(2))
    cliente._on_message(_mensaje(1))

    assert cliente.barras == [1, 2]
    assert cliente._ws.enviados == []


def test_sin_secuencia_en_el_mensaje_se_entrega_igual():
    cliente = _cliente_de_prueba()

    cliente._on_message(_mensaje(time=7))

    assert cliente.barras == [7]
