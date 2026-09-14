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


def test_publish_signals_skips_symbol_not_in_nuevos(monkeypatch):
    # Solo se publican simbolos en `nuevos` -- necesario para
    # Escaner.permitirMultiplesSenales: sin este filtro, un simbolo que
    # sigue calificando ciclo tras ciclo (ya no excluido por
    # _excluir_ya_senializados_hoy) publicaria un log nuevo cada ciclo
    # indefinidamente.
    fake = _FakeProducer()
    monkeypatch.setattr(kafka_producer, "_get_producer", lambda: fake)

    signals = {"AAPL": [_signal_match()]}
    kafka_producer.publish_signals(scanner_id=1, scanner_name="test", signals=signals, nuevos=set())

    assert fake.sent == []


def test_publish_signals_publishes_pre_filter_only_matches(monkeypatch):
    # Un escaner armado solo con filtros estaticos/dinamicos (sin ningun
    # filtro tecnico) llega a evaluar_tecnicos con grupos={} y devuelve
    # passed_matches=[] para cada simbolo -- eso NO significa "sin senal",
    # significa "confirmado solo por pre-filtros". Regresion para el bug
    # real visto en produccion con 'TEST POST MARKET'/'volumen test ':
    # `if not passed_matches: continue` descartaba esto en silencio.
    fake = _FakeProducer()
    monkeypatch.setattr(kafka_producer, "_get_producer", lambda: fake)

    signals = {"AAPL": []}
    kafka_producer.publish_signals(scanner_id=2, scanner_name="TEST POST MARKET", signals=signals, nuevos={"AAPL"})

    assert len(fake.sent) == 1
    topic, key, value = fake.sent[0]
    assert topic == "logs"
    assert key == "AAPL"
    assert value["mensaje"] == "Señal generada para AAPL en 'TEST POST MARKET'"
    assert value["metadatos"] is not None


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
