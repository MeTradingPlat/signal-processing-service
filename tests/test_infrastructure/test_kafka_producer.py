from datetime import datetime, timezone

import app.infrastructure.output.kafka_producer as kafka_producer
from app.models.enums import EnumFiltro
from app.models.filtro import Filtro
from app.models.signal_match import SignalMatch


class _FakeProducer:
    def __init__(self, raise_on_flush=None):
        self.sent = []
        self._raise_on_flush = raise_on_flush

    def send(self, topic, key=None, value=None):
        self.sent.append((topic, key, value))

    def flush(self, timeout=None):
        if self._raise_on_flush:
            raise self._raise_on_flush


def _signal_match():
    return SignalMatch(
        filtro=Filtro(enumFiltro=EnumFiltro.PRECIO),
        vela_timestamp=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
        precio=123.45,
    )


def test_publish_signals_sends_one_log_event_per_symbol(monkeypatch):
    fake = _FakeProducer()
    monkeypatch.setattr(kafka_producer, "_get_producer", lambda: fake)

    signals = {"AAPL": [_signal_match()]}
    kafka_producer.publish_signals(scanner_id=1, scanner_name="test", signals=signals, nuevos={"AAPL"})

    assert len(fake.sent) == 1
    topic, key, value = fake.sent[0]
    assert topic == "logs"
    assert key == "AAPL"
    assert value["categoria"] == "SIGNAL"
    assert value["idEscaner"] == 1
    assert value["symbol"] == "AAPL"
    assert value["esSenalNueva"] is True


def test_publish_signals_marks_symbol_not_new_when_absent_from_nuevos(monkeypatch):
    fake = _FakeProducer()
    monkeypatch.setattr(kafka_producer, "_get_producer", lambda: fake)

    signals = {"AAPL": [_signal_match()]}
    kafka_producer.publish_signals(scanner_id=1, scanner_name="test", signals=signals, nuevos=set())

    _, _, value = fake.sent[0]
    assert value["esSenalNueva"] is False


def test_publish_signals_flush_timeout_does_not_raise(monkeypatch):
    fake = _FakeProducer(raise_on_flush=TimeoutError("broker unreachable"))
    monkeypatch.setattr(kafka_producer, "_get_producer", lambda: fake)

    signals = {"AAPL": [_signal_match()]}
    kafka_producer.publish_signals(scanner_id=1, scanner_name="test", signals=signals, nuevos=set())


def test_publish_signals_with_no_producer_does_not_raise(monkeypatch):
    monkeypatch.setattr(kafka_producer, "_get_producer", lambda: False)

    signals = {"AAPL": [_signal_match()]}
    kafka_producer.publish_signals(scanner_id=1, scanner_name="test", signals=signals, nuevos=set())


def test_publish_scanner_state_sends_expected_shape(monkeypatch):
    fake = _FakeProducer()
    monkeypatch.setattr(kafka_producer, "_get_producer", lambda: fake)

    kafka_producer.publish_scanner_state(scanner_id=42, estado_nuevo="DETENIDO", razon="manual")

    assert len(fake.sent) == 1
    topic, key, value = fake.sent[0]
    assert topic == "scanner.state"
    assert key == "42"
    assert value["idEscaner"] == 42
    assert value["estadoNuevo"] == "DETENIDO"
    assert value["razon"] == "manual"
