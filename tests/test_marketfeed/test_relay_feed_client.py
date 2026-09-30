import json

from app.marketfeed.relay_feed_client import RelayFeedClient


class _Ws:
    def __init__(self):
        self.enviados = []

    def send(self, raw):
        self.enviados.append(json.loads(raw))


def _cliente_de_prueba(symbols=("AAPL", "MSFT")):
    cliente = RelayFeedClient.__new__(RelayFeedClient)
    cliente._data_key = "fundamentals"
    cliente._symbols = list(symbols)
    cliente._ws = _Ws()
    cliente._reconnect_attempts = 3
    cliente.recibidos = []
    cliente._on_update = lambda symbol, data: cliente.recibidos.append((symbol, data))
    return cliente


def test_on_open_suscribe_a_cada_simbolo_por_separado():
    cliente = _cliente_de_prueba()

    cliente._on_open()

    assert cliente._ws.enviados == [
        {"action": "subscribe", "symbol": "AAPL"},
        {"action": "subscribe", "symbol": "MSFT"},
    ]


def test_on_open_reinicia_el_contador_de_reintentos():
    cliente = _cliente_de_prueba()

    cliente._on_open()

    assert cliente._reconnect_attempts == 0


def test_on_message_entrega_el_dato_bajo_la_data_key_configurada():
    cliente = _cliente_de_prueba()
    msg = json.dumps({"type": "fundamentals", "symbol": "AAPL", "fundamentals": {"marketCap": 123}})

    cliente._on_message(msg)

    assert cliente.recibidos == [("AAPL", {"marketCap": 123})]


def test_on_message_ignora_un_mensaje_sin_la_data_key_configurada():
    cliente = _cliente_de_prueba()
    msg = json.dumps({"type": "snapshot", "symbol": "AAPL", "snapshot": {"currentPrice": 1.0}})

    cliente._on_message(msg)

    assert cliente.recibidos == []


def test_on_message_ignora_json_invalido_sin_lanzar():
    cliente = _cliente_de_prueba()

    cliente._on_message("no es json")

    assert cliente.recibidos == []
