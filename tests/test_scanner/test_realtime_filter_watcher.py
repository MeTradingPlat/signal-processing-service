from datetime import time

from app.models.enums import EnumCondicional, EnumEstadoEscaner, EnumFiltro, EnumParametro, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional, ValorFloat, ValorInteger, ValorString
from app.scanner.realtime_filter_watcher import RealtimeFilterWatcher


class _FakeCandleClient:
    """Reemplaza RealtimeCandleClient en los tests -- no abre ningun socket
    real, solo guarda las suscripciones pedidas y deja que el test dispare
    _on_history/_on_bar a mano."""

    def __init__(self, ws_url, on_history, on_bar, bars_for=None):
        self.ws_url = ws_url
        self.bars_for = bars_for
        self.on_history = on_history
        self.on_bar = on_bar
        self.subscriptions: set = set()
        self.stopped = False

    def update_subscriptions(self, keys):
        self.subscriptions = keys

    def stop(self):
        self.stopped = True


def _escaner() -> Escaner:
    return Escaner(
        idEscaner=1,
        nombre="test",
        horaInicio=time(9, 30, 0),
        horaFin=time(16, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.DIARIA),
    )


def _filtro_confirmation_candle() -> Filtro:
    return Filtro(
        enumFiltro=EnumFiltro.CONFIRMATION_CANDLE,
        parametros=[
            Parametro(enumParametro=EnumParametro.TIMEFRAME_CONFIRMATION_CANDLE,
                      objValorSeleccionado=ValorString(valor="_1M")),
            Parametro(enumParametro=EnumParametro.DIRECCION_CONFIRMATION_CANDLE,
                      objValorSeleccionado=ValorString(valor="ALCISTA")),
            Parametro(enumParametro=EnumParametro.PROPORCION_CUERPO_MINIMA_CONFIRMATION_CANDLE,
                      objValorSeleccionado=ValorFloat(valor=0.5)),
            # compute_value devuelve 0.0/1.0 -- IGUAL_A 1 es la condicion que
            # de verdad configura Java (ver FiltroFactoryConfirmationCandle).
            Parametro(enumParametro=EnumParametro.CONDICION,
                      objValorSeleccionado=ValorCondicional(enumCondicional=EnumCondicional.IGUAL_A, valor1=1.0)),
        ],
    )


def _filtro_percentage_change() -> Filtro:
    """PERCENTAGE_CHANGE con MAYOR_QUE 0 -- pasa si la ultima vela cerro por
    encima de la primera del lote, simple y determinista para probar el
    encadenamiento entre grupos (a diferencia de CONFIRMATION_CANDLE, que
    necesita un patron de 3 velas puntual)."""
    return Filtro(
        enumFiltro=EnumFiltro.PERCENTAGE_CHANGE,
        parametros=[
            Parametro(enumParametro=EnumParametro.CONDICION,
                      objValorSeleccionado=ValorCondicional(enumCondicional=EnumCondicional.MAYOR_QUE, valor1=0.0)),
        ],
    )


def _make_watcher():
    published = []
    watcher = RealtimeFilterWatcher(
        _escaner(), "ws://marketdata-service:8082/ws/candles",
        publish_signal=lambda escaner, symbol, matches: published.append((symbol, matches)),
        client_factory=_FakeCandleClient,
    )
    return watcher, published


def test_actualizar_universo_suscribe_al_primer_grupo():
    watcher, _ = _make_watcher()
    watcher.configurar_grupos({1: [_filtro_confirmation_candle()]})

    watcher.actualizar_universo({"AAPL", "MSFT"})

    assert watcher._client.subscriptions == {("AAPL", "M1"), ("MSFT", "M1")}


def test_bar_cerrada_que_confirma_publica_senal():
    watcher, published = _make_watcher()
    watcher.configurar_grupos({1: [_filtro_confirmation_candle()]})
    watcher.actualizar_universo({"AAPL"})

    # 3 velas: imbalance de 3 velas (igual que Order Block) entre la 1 y la
    # 3, mas vela de poder en la 3 (cuerpo/rango >= 0.5, sin solape con la 1).
    watcher._client.on_history("AAPL", "M1", [
        {"time": 1_700_000_000, "open": 10, "high": 10, "low": 9, "close": 9.5, "closed": True},
        {"time": 1_700_000_060, "open": 9.5, "high": 10.5, "low": 9.5, "close": 10, "closed": True},
    ])
    watcher._client.on_bar("AAPL", "M1", {
        "time": 1_700_000_120, "open": 11, "high": 15, "low": 11, "close": 15, "closed": True,
    })

    assert len(published) == 1
    symbol, matches = published[0]
    assert symbol == "AAPL"
    assert len(matches) == 1
    assert matches[0].filtro.enumFiltro == EnumFiltro.CONFIRMATION_CANDLE
    assert matches[0].precio == 15


def test_bar_cerrada_que_no_confirma_no_publica():
    watcher, published = _make_watcher()
    watcher.configurar_grupos({1: [_filtro_confirmation_candle()]})
    watcher.actualizar_universo({"AAPL"})

    watcher._client.on_history("AAPL", "M1", [
        {"time": 1_700_000_000, "open": 10, "high": 10, "low": 9, "close": 9.5, "closed": True},
        {"time": 1_700_000_060, "open": 9.5, "high": 10.5, "low": 9.5, "close": 10, "closed": True},
    ])
    # Cuerpo chico, no supera la proporcion minima configurada (0.5).
    watcher._client.on_bar("AAPL", "M1", {
        "time": 1_700_000_120, "open": 11, "high": 15, "low": 9, "close": 11.5, "closed": True,
    })

    assert published == []


def test_tick_parcial_se_ignora_no_evalua_ni_publica():
    """/ws/candles manda un mensaje por cada tick de la vela en formacion
    (closed=false) antes del cierre real -- no debe evaluarse el filtro ni
    contaminar el buffer de velas hasta que llegue closed=true."""
    watcher, published = _make_watcher()
    watcher.configurar_grupos({1: [_filtro_confirmation_candle()]})
    watcher.actualizar_universo({"AAPL"})
    watcher._client.on_history("AAPL", "M1", [
        {"time": 1_700_000_000, "open": 10, "high": 10, "low": 9, "close": 9.5, "closed": True},
        {"time": 1_700_000_060, "open": 9.5, "high": 10.5, "low": 9.5, "close": 10, "closed": True},
    ])

    # Tick parcial de la vela que todavia se esta formando -- se ignora.
    watcher._client.on_bar("AAPL", "M1", {
        "time": 1_700_000_120, "open": 11, "high": 15, "low": 11, "close": 15, "closed": False,
    })
    assert published == []
    assert len(watcher._candles[("AAPL", "M1")]) == 2

    # Recien al cerrar de verdad se evalua y publica.
    watcher._client.on_bar("AAPL", "M1", {
        "time": 1_700_000_120, "open": 11, "high": 15, "low": 11, "close": 15, "closed": True,
    })
    assert len(published) == 1
    assert len(watcher._candles[("AAPL", "M1")]) == 3


def test_stop_delega_al_cliente():
    watcher, _ = _make_watcher()
    watcher.stop()
    assert watcher._client.stopped is True


def _pasar_d1(watcher, symbol="AAPL", suba=True):
    """Cierra una vela D1 que pasa (suba=True) o falla (suba=False) el
    filtro PERCENTAGE_CHANGE > 0 configurado en el grupo D1 de los tests de
    encadenamiento."""
    open_ = 100
    close = 110 if suba else 90
    watcher._client.on_history(symbol, "D1", [
        {"time": 1_700_000_000, "open": open_, "high": open_, "low": open_, "close": open_, "closed": True},
    ])
    watcher._client.on_bar(symbol, "D1", {
        "time": 1_700_086_400, "open": open_, "high": max(open_, close), "low": min(open_, close),
        "close": close, "closed": True,
    })


def test_cadena_multigrupo_promueve_y_publica_al_completar():
    """D1 (grueso) -> M1 (fino): solo se suscribe a M1 despues de pasar D1,
    y la señal publicada trae los matches de AMBOS grupos -- igual que
    evaluar_tecnicos ensamblaria en una sola pasada batch."""
    watcher, published = _make_watcher()
    watcher.configurar_grupos({1440: [_filtro_percentage_change()], 1: [_filtro_percentage_change()]})
    watcher.actualizar_universo({"AAPL"})

    assert watcher._client.subscriptions == {("AAPL", "D1")}

    _pasar_d1(watcher, suba=True)
    assert published == []
    assert watcher._client.subscriptions == {("AAPL", "D1"), ("AAPL", "M1")}

    watcher._client.on_history("AAPL", "M1", [
        {"time": 1_700_100_000, "open": 50, "high": 50, "low": 50, "close": 50, "closed": True},
    ])
    watcher._client.on_bar("AAPL", "M1", {
        "time": 1_700_100_060, "open": 50, "high": 65, "low": 50, "close": 65, "closed": True,
    })

    assert len(published) == 1
    symbol, matches = published[0]
    assert symbol == "AAPL"
    assert len(matches) == 2


def test_simbolo_ya_calificando_no_republica_al_repetir_vela_fina():
    watcher, published = _make_watcher()
    watcher.configurar_grupos({1440: [_filtro_percentage_change()], 1: [_filtro_percentage_change()]})
    watcher.actualizar_universo({"AAPL"})
    _pasar_d1(watcher, suba=True)
    watcher._client.on_history("AAPL", "M1", [
        {"time": 1_700_100_000, "open": 50, "high": 50, "low": 50, "close": 50, "closed": True},
    ])
    watcher._client.on_bar("AAPL", "M1", {
        "time": 1_700_100_060, "open": 50, "high": 65, "low": 50, "close": 65, "closed": True,
    })
    assert len(published) == 1

    # Otra vela M1 que sigue calificando -- no debe volver a publicar.
    watcher._client.on_bar("AAPL", "M1", {
        "time": 1_700_100_120, "open": 65, "high": 70, "low": 65, "close": 70, "closed": True,
    })

    assert len(published) == 1


def test_grupo_grueso_que_deja_de_calificar_degrada_y_desuscribe():
    watcher, published = _make_watcher()
    watcher.configurar_grupos({1440: [_filtro_percentage_change()], 1: [_filtro_percentage_change()]})
    watcher.actualizar_universo({"AAPL"})
    _pasar_d1(watcher, suba=True)
    assert watcher._client.subscriptions == {("AAPL", "D1"), ("AAPL", "M1")}

    # Al dia siguiente cierra una nueva D1 que ya NO pasa -- degrada al
    # simbolo y lo desuscribe de M1, sin esperar a que M1 haga nada.
    watcher._client.on_bar("AAPL", "D1", {
        "time": 1_700_172_800, "open": 110, "high": 110, "low": 90, "close": 90, "closed": True,
    })

    assert watcher._client.subscriptions == {("AAPL", "D1")}
    assert published == []


def test_simbolo_que_sale_del_universo_libera_su_buffer_de_velas():
    watcher, _ = _make_watcher()
    watcher.configurar_grupos({1: [_filtro_confirmation_candle()]})
    watcher.actualizar_universo({"AAPL", "MSFT"})
    for symbol in ("AAPL", "MSFT"):
        watcher._client.on_history(symbol, "M1", [
            {"time": 1_700_000_000, "open": 10, "high": 10, "low": 9, "close": 9.5, "closed": True},
        ])
    assert watcher.buffer_stats() == (2, 2)

    watcher.actualizar_universo({"AAPL"})

    assert watcher.buffer_stats() == (1, 1)


def _filtro_volume_spike(n_velas: int) -> Filtro:
    return Filtro(
        enumFiltro=EnumFiltro.VOLUME_SPIKE,
        parametros=[Parametro(enumParametro=EnumParametro.NUMERO_VELAS_VOLUME_SPIKE,
                              objValorSeleccionado=ValorInteger(valor=n_velas))],
    )


def test_barras_pedidas_dependen_de_la_config_de_los_filtros_del_grupo():
    watcher, _ = _make_watcher()
    watcher.configurar_grupos({1: [_filtro_confirmation_candle()], 5: [_filtro_volume_spike(300)]})

    assert watcher._bars_for("M1") == 151
    assert watcher._bars_for("M5") == 302


def test_barras_pedidas_se_acotan_al_maximo_permitido():
    watcher, _ = _make_watcher()
    watcher.configurar_grupos({1: [_filtro_volume_spike(50_000)]})

    assert watcher._bars_for("M1") == 2000


def test_cliente_recibe_la_funcion_que_calcula_las_barras():
    watcher, _ = _make_watcher()
    watcher.configurar_grupos({1: [_filtro_volume_spike(40)]})

    assert watcher._client.bars_for("M1") == 151


def test_historial_inicial_se_recorta_al_maximo_del_buffer():
    watcher, _ = _make_watcher()
    watcher.configurar_grupos({1: [_filtro_confirmation_candle()]})
    watcher.actualizar_universo({"AAPL"})
    bars = [
        {"time": 1_700_000_000 + i * 60, "open": 10, "high": 11, "low": 9, "close": 10, "closed": True}
        for i in range(500)
    ]

    watcher._client.on_history("AAPL", "M1", bars)

    assert watcher.buffer_stats() == (1, 151)
    ultima = watcher._candles[("AAPL", "M1")][-1]
    assert int(ultima.timestamp.timestamp()) == 1_700_000_000 + 499 * 60
