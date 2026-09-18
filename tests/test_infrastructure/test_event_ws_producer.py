from datetime import datetime, timezone

import app.infrastructure.output.event_ws_producer as event_ws_producer
from app.models.enums import EnumFiltro
from app.models.filtro import Filtro
from app.models.signal_match import SignalMatch


class _FakeClient:
    def __init__(self, raise_on_send=None):
        self.sent = []
        self._raise_on_send = raise_on_send

    def send(self, payload):
        if self._raise_on_send:
            raise self._raise_on_send
        self.sent.append(payload)


def _signal_match():
    return SignalMatch(
        filtro=Filtro(enumFiltro=EnumFiltro.PRECIO),
        vela_timestamp=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
        precio=123.45,
    )


def test_publish_signals_sends_one_log_event_per_symbol(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(event_ws_producer, "_log_service_client", fake)

    signals = {"AAPL": [_signal_match()]}
    event_ws_producer.publish_signals(scanner_id=1, scanner_name="test", signals=signals, nuevos={"AAPL"})

    assert len(fake.sent) == 1
    value = fake.sent[0]
    assert value["categoria"] == "SIGNAL"
    assert value["idEscaner"] == 1
    assert value["symbol"] == "AAPL"
    assert value["esSenalNueva"] is True


def test_publish_signals_skips_symbol_not_in_nuevos(monkeypatch):
    # Solo se publican simbolos en `nuevos` -- necesario para
    # Escaner.permitirMultiplesSenales: sin este filtro, un simbolo que
    # sigue calificando ciclo tras ciclo (ya no excluido por
    # _excluir_ya_senializados_hoy) publicaria un log nuevo cada ciclo
    # indefinidamente.
    fake = _FakeClient()
    monkeypatch.setattr(event_ws_producer, "_log_service_client", fake)

    signals = {"AAPL": [_signal_match()]}
    event_ws_producer.publish_signals(scanner_id=1, scanner_name="test", signals=signals, nuevos=set())

    assert fake.sent == []


def test_publish_signals_publishes_pre_filter_only_matches(monkeypatch):
    # Un escaner armado solo con filtros estaticos/dinamicos (sin ningun
    # filtro tecnico) llega a evaluar_tecnicos con grupos={} y devuelve
    # passed_matches=[] para cada simbolo -- eso NO significa "sin senal",
    # significa "confirmado solo por pre-filtros".
    fake = _FakeClient()
    monkeypatch.setattr(event_ws_producer, "_log_service_client", fake)

    signals = {"AAPL": []}
    event_ws_producer.publish_signals(scanner_id=2, scanner_name="TEST POST MARKET", signals=signals,
                                       nuevos={"AAPL"})

    assert len(fake.sent) == 1
    value = fake.sent[0]
    assert value["mensaje"] == "Señal generada para AAPL en 'TEST POST MARKET'"
    assert value["metadatos"] is not None


def test_publish_signals_continues_after_a_failed_send(monkeypatch):
    # Un envio WS no bloquea (a diferencia del viejo KafkaProducer, que podia
    # colgar cada send() hasta max_block_ms esperando metadata) -- un fallo
    # puntual no debe frenar el resto del lote.
    fake = _FakeClient(raise_on_send=RuntimeError("connection closed"))
    monkeypatch.setattr(event_ws_producer, "_log_service_client", fake)

    signals = {"AAPL": [_signal_match()], "MSFT": [_signal_match()]}
    event_ws_producer.publish_signals(scanner_id=1, scanner_name="test", signals=signals,
                                       nuevos={"AAPL", "MSFT"})

    assert fake.sent == []


def test_publish_scanner_state_sends_to_both_clients(monkeypatch):
    fake_notification = _FakeClient()
    fake_scanner_mgmt = _FakeClient()
    monkeypatch.setattr(event_ws_producer, "_notification_service_client", fake_notification)
    monkeypatch.setattr(event_ws_producer, "_scanner_management_client", fake_scanner_mgmt)

    event_ws_producer.publish_scanner_state(scanner_id=42, estado_nuevo="DETENIDO", razon="manual")

    for fake in (fake_notification, fake_scanner_mgmt):
        assert len(fake.sent) == 1
        value = fake.sent[0]
        assert value["idEscaner"] == 42
        assert value["estadoNuevo"] == "DETENIDO"
        assert value["razon"] == "manual"
