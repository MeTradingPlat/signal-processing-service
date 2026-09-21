from array import array
from datetime import datetime, timedelta, timezone

from app.models.enums import EnumFiltro
from app.models.filtro import Filtro
from app.scanner import timeframe as tf
from app.scanner.buffered_candle import BufferedCandle
from app.scanner.day_summary import DaySummary
from app.scanner.marketdata_client import MarketdataClient
from app.scanner.realtime_filter_watcher import RealtimeFilterWatcher
from app.scanner.volume_profile import VolumeProfile
from app.strategies.base import MarketData
from app.strategies.patrones import FirstCandleStrategy, HighLowOfDayStrategy, OpeningRangeBreakoutStrategy
from app.strategies.volumen.relative_volume_same_time import RelativeVolumeSameTimeStrategy
from tests.test_scanner.test_realtime_filter_watcher import _FakeCandleClient, _escaner


def _bar_dict(minute_offset: int, high=2.0, low=1.0, volume=10) -> dict:
    base = int(datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc).timestamp())
    return {"time": base + minute_offset * 60, "open": 1.5, "high": high, "low": low, "close": 1.5,
            "volume": volume, "closed": True}


def _candle(high=2.0, low=1.0, close=1.5, volume=10.0, minute=0) -> BufferedCandle:
    ts = datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc) + timedelta(minutes=minute)
    return BufferedCandle(symbol="AAPL", timestamp=ts, open=1.5, high=high, low=low, close=close, volume=volume)


def _watcher(filtro: Filtro, profile_loader=None):
    watcher = RealtimeFilterWatcher(
        _escaner(), "ws://x/ws/candles", publish_signal=lambda *a: None,
        client_factory=_FakeCandleClient, profile_loader=profile_loader,
    )
    watcher.configurar_grupos({1: [filtro]})
    return watcher


def test_los_filtros_del_dia_piden_la_sesion_pero_solo_guardan_el_piso(monkeypatch):
    monkeypatch.setattr(tf, "_barras_para_cubrir_sesion", lambda minutos: 800)
    filtros = [Filtro(enumFiltro=EnumFiltro.HIGH_LOW_OF_DAY)]

    assert tf.bars_historial_grupo(filtros, 1) == 800
    assert tf.bars_buffer_grupo(filtros, 1) == 150


def test_el_volumen_relativo_ya_no_pide_cinco_dias_de_velas(monkeypatch):
    monkeypatch.setattr(tf, "_barras_para_cubrir_sesion", lambda minutos: 600)
    filtros = [Filtro(enumFiltro=EnumFiltro.RELATIVE_VOLUME_SAME_TIME)]

    assert tf.bars_historial_grupo(filtros, 1) == 600
    assert tf.bars_historial_grupo(filtros, 1) < tf.bars_necesarias_grupo(filtros, 1)


def test_el_historial_siembra_el_resumen_completo_aunque_el_buffer_se_recorte():
    watcher = _watcher(Filtro(enumFiltro=EnumFiltro.HIGH_LOW_OF_DAY))
    bars = [_bar_dict(i, high=5.0, low=1.0, volume=10) for i in range(300)]
    bars[3]["high"] = 99.0

    watcher._on_history("AAPL", "M1", bars)

    resumen = watcher._state.day("AAPL", "M1")
    assert (resumen.high, resumen.volume) == (99.0, 3000)
    assert watcher.buffer_stats() == (1, 151)


def test_cada_vela_cerrada_actualiza_el_resumen_del_dia():
    watcher = _watcher(Filtro(enumFiltro=EnumFiltro.HIGH_LOW_OF_DAY))
    watcher._on_history("AAPL", "M1", [_bar_dict(0, high=5.0, volume=10)])

    watcher._on_bar("AAPL", "M1", _bar_dict(1, high=8.0, volume=30))

    resumen = watcher._state.day("AAPL", "M1")
    assert (resumen.high, resumen.volume) == (8.0, 40)


def test_un_grupo_sin_filtros_del_dia_no_guarda_resumen():
    watcher = _watcher(Filtro(enumFiltro=EnumFiltro.PIVOTS))

    watcher._on_history("AAPL", "M1", [_bar_dict(0)])

    assert watcher._state.day("AAPL", "M1") is None


def test_el_perfil_se_pide_una_vez_por_simbolo_y_timeframe():
    llamadas = []

    def loader(symbols, timeframe):
        llamadas.append((sorted(symbols), timeframe))
        return {"AAPL": VolumeProfile(slot_minutes=1, cumulative=array("f", [1.0]))}

    watcher = _watcher(Filtro(enumFiltro=EnumFiltro.RELATIVE_VOLUME_SAME_TIME), loader)

    watcher.actualizar_universo({"AAPL", "MSFT"})
    watcher.actualizar_universo({"AAPL", "MSFT"})

    assert llamadas == [(["AAPL", "MSFT"], "M1")]
    assert watcher._state.profile("AAPL", "M1") is not None
    assert watcher._state.profile("MSFT", "M1") is None


def test_un_error_al_cargar_perfiles_no_rompe_el_ciclo():
    def loader(symbols, timeframe):
        raise RuntimeError("marketdata caido")

    watcher = _watcher(Filtro(enumFiltro=EnumFiltro.RELATIVE_VOLUME_SAME_TIME), loader)

    watcher.actualizar_universo({"AAPL"})

    assert watcher._client.subscriptions == {("AAPL", "M1")}


def test_sin_filtro_de_volumen_relativo_no_se_pide_ningun_perfil():
    llamadas = []
    watcher = _watcher(Filtro(enumFiltro=EnumFiltro.HIGH_LOW_OF_DAY), lambda s, t: llamadas.append(s) or {})

    watcher.actualizar_universo({"AAPL"})

    assert llamadas == []


def _resumen(first: BufferedCandle, high=10.0, low=1.0, volume=0.0) -> DaySummary:
    return DaySummary(session=20260918, first=first, high=high, low=low, volume=volume)


def test_la_primera_vela_del_dia_sale_del_resumen_aunque_ya_no_este_en_el_buffer():
    primera = _candle(close=2.0)
    data = MarketData(symbol="AAPL", candles=[_candle(close=1.0, minute=200)], day=_resumen(primera))

    assert FirstCandleStrategy(Filtro(enumFiltro=EnumFiltro.FIRST_CANDLE)).compute_value(data) == 1.0


def test_maximo_y_minimo_del_dia_salen_del_resumen():
    data = MarketData(symbol="AAPL", candles=[_candle(close=7.0, minute=200)],
                      day=_resumen(_candle(), high=10.0, low=4.0))

    assert HighLowOfDayStrategy(Filtro(enumFiltro=EnumFiltro.HIGH_LOW_OF_DAY)).compute_value(data) == 50.0


def test_ruptura_del_rango_de_apertura_usa_la_primera_vela_del_resumen():
    primera = _candle(high=5.0, low=3.0)
    data = MarketData(symbol="AAPL", candles=[_candle(close=6.0, minute=200)], day=_resumen(primera))

    assert OpeningRangeBreakoutStrategy(Filtro(enumFiltro=EnumFiltro.OPENING_RANGE_BREAKOUT)).compute_value(data) == 1.0


def test_volumen_relativo_compara_el_acumulado_del_dia_contra_el_perfil():
    perfil = VolumeProfile(slot_minutes=1, cumulative=array("f", [1000.0] * 960))
    data = MarketData(symbol="AAPL", candles=[_candle(minute=0)], day=_resumen(_candle(), volume=1500.0),
                      volume_profile=perfil)

    assert RelativeVolumeSameTimeStrategy(Filtro(enumFiltro=EnumFiltro.RELATIVE_VOLUME_SAME_TIME)).compute_value(data) == 150.0


def test_volumen_relativo_sin_perfil_para_esa_hora_no_califica():
    perfil = VolumeProfile(slot_minutes=1, cumulative=array("f", [0.0] * 960))
    data = MarketData(symbol="AAPL", candles=[_candle(minute=0)], day=_resumen(_candle(), volume=10.0),
                      volume_profile=perfil)

    assert RelativeVolumeSameTimeStrategy(Filtro(enumFiltro=EnumFiltro.RELATIVE_VOLUME_SAME_TIME)).compute_value(data) is None


def test_el_cliente_convierte_la_respuesta_en_perfiles(monkeypatch):
    client = MarketdataClient.__new__(MarketdataClient)
    pedidos = []

    def fake_request(method, path, body=None, timeout=None):
        pedidos.append((method, path, body))
        return {"profiles": {"AAPL": {"slotMinutes": 5, "sessions": 20, "cumulative": [10, 20, 30]}}}

    monkeypatch.setattr(client, "_request", fake_request, raising=False)

    perfiles = client.fetch_volume_profiles(["AAPL"], "M5")

    assert pedidos[0][:2] == ("POST", "/marketdata/volume-profile")
    assert perfiles["AAPL"].slot_minutes == 5
    assert list(perfiles["AAPL"].cumulative) == [10.0, 20.0, 30.0]


def test_los_simbolos_sin_perfil_se_reintentan_pasado_el_intervalo(monkeypatch):
    from app.scanner import session_state

    reloj = [1000.0]
    monkeypatch.setattr(session_state.time, "monotonic", lambda: reloj[0])
    llamadas = []

    def loader(symbols, timeframe):
        llamadas.append(sorted(symbols))
        return {"AAPL": VolumeProfile(slot_minutes=1, cumulative=array("f", [1.0]))} if len(llamadas) == 1 else {
            "MSFT": VolumeProfile(slot_minutes=1, cumulative=array("f", [1.0]))}

    watcher = _watcher(Filtro(enumFiltro=EnumFiltro.RELATIVE_VOLUME_SAME_TIME), loader)

    watcher.actualizar_universo({"AAPL", "MSFT"})
    reloj[0] += 60
    watcher.actualizar_universo({"AAPL", "MSFT"})
    reloj[0] += 900
    watcher.actualizar_universo({"AAPL", "MSFT"})

    assert llamadas == [["AAPL", "MSFT"], ["MSFT"]]
    assert watcher._state.profile("MSFT", "M1") is not None


def test_un_error_del_cargador_se_reintenta_al_minuto(monkeypatch):
    from app.scanner import session_state

    reloj = [1000.0]
    monkeypatch.setattr(session_state.time, "monotonic", lambda: reloj[0])
    intentos = []

    def loader(symbols, timeframe):
        intentos.append(1)
        raise RuntimeError("caido")

    watcher = _watcher(Filtro(enumFiltro=EnumFiltro.RELATIVE_VOLUME_SAME_TIME), loader)

    watcher.actualizar_universo({"AAPL"})
    watcher.actualizar_universo({"AAPL"})
    reloj[0] += 61
    watcher.actualizar_universo({"AAPL"})

    assert len(intentos) == 2


def test_un_cambio_de_grupo_ajusta_solo_las_suscripciones_de_ese_simbolo():
    watcher = RealtimeFilterWatcher(
        _escaner(), "ws://x/ws/candles", publish_signal=lambda *a: None, client_factory=_FakeCandleClient)
    watcher.configurar_grupos({60: [Filtro(enumFiltro=EnumFiltro.PIVOTS)], 1: [Filtro(enumFiltro=EnumFiltro.PIVOTS)]})
    watcher.actualizar_universo({"AAPL", "MSFT"})
    completas = watcher._client.update_subscriptions
    llamadas = []
    watcher._client.update_subscriptions = lambda keys: (llamadas.append(keys), completas(keys))

    watcher._stage["AAPL"] = 1
    watcher._resuscribir_symbol("AAPL")

    assert llamadas == []
    assert watcher._client.subscriptions == {("AAPL", "H1"), ("AAPL", "M1"), ("MSFT", "H1")}
    assert watcher._client.cambios == 1


def test_degradar_un_simbolo_quita_solo_sus_suscripciones_finas_y_su_buffer():
    watcher = RealtimeFilterWatcher(
        _escaner(), "ws://x/ws/candles", publish_signal=lambda *a: None, client_factory=_FakeCandleClient)
    watcher.configurar_grupos({60: [Filtro(enumFiltro=EnumFiltro.PIVOTS)], 1: [Filtro(enumFiltro=EnumFiltro.PIVOTS)]})
    watcher.actualizar_universo({"AAPL", "MSFT"})
    watcher._stage["AAPL"] = 1
    watcher._resuscribir_symbol("AAPL")
    watcher._on_history("AAPL", "M1", [_bar_dict(0)])

    watcher._degradar("AAPL", 0)

    assert watcher._client.subscriptions == {("AAPL", "H1"), ("MSFT", "H1")}
    assert ("AAPL", "M1") not in watcher._candles


def test_barras_y_ciclos_concurrentes_no_rompen_el_estado_del_watcher():
    import threading

    watcher = RealtimeFilterWatcher(
        _escaner(), "ws://x/ws/candles", publish_signal=lambda *a: None, client_factory=_FakeCandleClient)
    watcher.configurar_grupos({60: [Filtro(enumFiltro=EnumFiltro.PIVOTS)], 1: [Filtro(enumFiltro=EnumFiltro.PIVOTS)]})
    universo = {f"S{i}" for i in range(300)}
    watcher.actualizar_universo(universo)
    errores, parar = [], threading.Event()

    def barras():
        k = 0
        while not parar.is_set():
            for i in range(300):
                for tf in ("H1", "M1"):
                    try:
                        watcher._on_bar(f"S{i}", tf, _bar_dict(k, high=1.0 + (i + k) % 7))
                    except Exception as e:
                        errores.append(repr(e))
            k += 1

    hilo = threading.Thread(target=barras)
    hilo.start()
    for i in range(60):
        watcher.actualizar_universo(universo if i % 2 == 0 else set(list(universo)[:250]))
    parar.set()
    hilo.join()

    assert errores == []


def test_una_correccion_reemplaza_la_vela_del_buffer_y_ajusta_el_resumen_del_dia():
    watcher = _watcher(Filtro(enumFiltro=EnumFiltro.HIGH_LOW_OF_DAY))
    watcher._on_history("AAPL", "M1", [_bar_dict(0, high=5.0, volume=100), _bar_dict(1, high=6.0, volume=30)])

    corregida = _bar_dict(0, high=7.0, volume=120)
    corregida["corrected"] = True
    watcher._on_bar("AAPL", "M1", corregida)

    buffer = watcher._candles[("AAPL", "M1")]
    resumen = watcher._state.day("AAPL", "M1")
    assert len(buffer) == 2 and buffer[0].volume == 120 and buffer[0].high == 7.0
    assert (resumen.volume, resumen.high) == (150, 7.0)
    assert resumen.first.volume == 120


class _EstrategiaVolumenMinimo:
    def __init__(self, minimo):
        self.minimo = minimo
        self.evaluaciones = 0

    def evaluate(self, data):
        self.evaluaciones += 1
        return data.candles[-1].volume >= self.minimo


def _watcher_con_estrategia(monkeypatch, estrategia):
    from app.scanner import realtime_filter_watcher as modulo

    llamadas = []
    monkeypatch.setattr(modulo, "get_strategy", lambda f: llamadas.append(f) or estrategia)
    publicadas = []
    watcher = RealtimeFilterWatcher(
        _escaner(), "ws://x/ws/candles", publish_signal=lambda esc, symbol, matches: publicadas.append(symbol),
        client_factory=_FakeCandleClient)
    watcher.configurar_grupos({1: [Filtro(enumFiltro=EnumFiltro.PIVOTS)]})
    watcher.actualizar_universo({"AAPL"})
    return watcher, publicadas, llamadas


def _corregida(minuto, volume):
    bar = _bar_dict(minuto, volume=volume)
    bar["corrected"] = True
    return bar


def test_una_correccion_de_la_ultima_vela_publica_la_senal_que_la_vela_original_no_alcanzo(monkeypatch):
    watcher, publicadas, _ = _watcher_con_estrategia(monkeypatch, _EstrategiaVolumenMinimo(100))
    watcher._on_history("AAPL", "M1", [_bar_dict(0)])
    watcher._on_bar("AAPL", "M1", _bar_dict(1, volume=50))
    assert publicadas == []

    watcher._on_bar("AAPL", "M1", _corregida(1, 150))
    watcher._on_bar("AAPL", "M1", _corregida(1, 160))

    assert publicadas == ["AAPL"]
    assert len(watcher._candles[("AAPL", "M1")]) == 2


def test_una_correccion_que_hace_fallar_a_un_simbolo_no_retira_la_senal_ya_publicada(monkeypatch):
    watcher, publicadas, _ = _watcher_con_estrategia(monkeypatch, _EstrategiaVolumenMinimo(100))
    watcher._on_history("AAPL", "M1", [_bar_dict(0)])
    watcher._on_bar("AAPL", "M1", _bar_dict(1, volume=150))
    assert publicadas == ["AAPL"]

    watcher._on_bar("AAPL", "M1", _corregida(1, 40))

    assert publicadas == ["AAPL"]
    assert "AAPL" not in watcher._signaling


def test_una_correccion_de_una_vela_que_no_es_la_ultima_no_reevalua(monkeypatch):
    estrategia = _EstrategiaVolumenMinimo(100)
    watcher, publicadas, _ = _watcher_con_estrategia(monkeypatch, estrategia)
    watcher._on_history("AAPL", "M1", [_bar_dict(0), _bar_dict(1)])
    watcher._on_bar("AAPL", "M1", _bar_dict(2, volume=10))
    antes = estrategia.evaluaciones

    watcher._on_bar("AAPL", "M1", _corregida(0, 999))

    assert estrategia.evaluaciones == antes
    assert publicadas == []


def test_las_estrategias_de_un_grupo_se_crean_una_sola_vez(monkeypatch):
    watcher, _, llamadas = _watcher_con_estrategia(monkeypatch, _EstrategiaVolumenMinimo(1000))
    watcher._on_history("AAPL", "M1", [_bar_dict(0)])

    for minuto in range(1, 6):
        watcher._on_bar("AAPL", "M1", _bar_dict(minuto))

    assert len(llamadas) == 1


def test_una_correccion_de_una_vela_que_ya_salio_del_buffer_se_ignora():
    watcher = _watcher(Filtro(enumFiltro=EnumFiltro.HIGH_LOW_OF_DAY))
    watcher._on_history("AAPL", "M1", [_bar_dict(5, volume=10)])

    corregida = _bar_dict(0, volume=999)
    corregida["corrected"] = True
    watcher._on_bar("AAPL", "M1", corregida)

    assert [c.volume for c in watcher._candles[("AAPL", "M1")]] == [10]
    assert watcher._state.day("AAPL", "M1").volume == 10
