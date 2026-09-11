from datetime import time

from app.models.enums import EnumCondicional, EnumEstadoEscaner, EnumFiltro, EnumParametro, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.models.filtro import Filtro, Parametro
from app.models.valor import ValorCondicional, ValorFloat, ValorString
from app.scanner.realtime_filter_watcher import RealtimeFilterWatcher


class _FakeCandleClient:
    """Reemplaza RealtimeCandleClient en los tests -- no abre ningun socket
    real, solo guarda las suscripciones pedidas y deja que el test dispare
    _on_history/_on_bar a mano."""

    def __init__(self, ws_url, on_history, on_bar):
        self.ws_url = ws_url
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
        revisionTiempoReal=True,
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


def _make_watcher():
    published = []
    watcher = RealtimeFilterWatcher(
        _escaner(), "ws://marketdata-service:8082/ws/candles",
        publish_signal=lambda escaner, symbol, match: published.append((symbol, match)),
        client_factory=_FakeCandleClient,
    )
    return watcher, published


def test_actualizar_suscribe_a_los_candidatos_del_grupo_del_filtro():
    watcher, _ = _make_watcher()
    filtro = _filtro_confirmation_candle()

    watcher.actualizar([filtro], candidatos_previos_a_grupo={1: {"AAPL", "MSFT"}, 240: {"AAPL"}})

    assert watcher._client.subscriptions == {("AAPL", "M1"), ("MSFT", "M1")}


def test_bar_cerrada_que_confirma_publica_senal():
    watcher, published = _make_watcher()
    filtro = _filtro_confirmation_candle()
    watcher.actualizar([filtro], candidatos_previos_a_grupo={1: {"AAPL"}})

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
    symbol, match = published[0]
    assert symbol == "AAPL"
    assert match.filtro.enumFiltro == EnumFiltro.CONFIRMATION_CANDLE
    assert match.precio == 15


def test_bar_cerrada_que_no_confirma_no_publica():
    watcher, published = _make_watcher()
    filtro = _filtro_confirmation_candle()
    watcher.actualizar([filtro], candidatos_previos_a_grupo={1: {"AAPL"}})

    watcher._client.on_history("AAPL", "M1", [
        {"time": 1_700_000_000, "open": 10, "high": 10, "low": 9, "close": 9.5, "closed": True},
        {"time": 1_700_000_060, "open": 9.5, "high": 10.5, "low": 9.5, "close": 10, "closed": True},
    ])
    # Cuerpo chico, no supera la proporcion minima configurada (0.5).
    watcher._client.on_bar("AAPL", "M1", {
        "time": 1_700_000_120, "open": 11, "high": 15, "low": 9, "close": 11.5, "closed": True,
    })

    assert published == []


def test_stop_delega_al_cliente():
    watcher, _ = _make_watcher()
    watcher.stop()
    assert watcher._client.stopped is True
