import json

import app.infrastructure.output.outbound_event_ws_client as client_module
from app.infrastructure.output.outbound_event_ws_client import OutboundEventWebSocketClient


class _FakeWs:
    def __init__(self, fail_after=None):
        self.sent = []
        self._fail_after = fail_after

    def send(self, message):
        if self._fail_after is not None and len(self.sent) >= self._fail_after:
            raise OSError("socket is already closed")
        self.sent.append(message)


def _client():
    return OutboundEventWebSocketClient("ws://test", "test", start=False)


def _connect(client, ws):
    client._ws = ws
    client._on_open()


def test_send_before_connect_is_queued_and_delivered_in_order_on_open():
    client = _client()
    for i in range(340):
        client.send({"n": i})
    assert client.pending_count() == 340

    ws = _FakeWs()
    _connect(client, ws)

    assert [json.loads(m)["n"] for m in ws.sent] == list(range(340))
    assert client.pending_count() == 0


def test_send_when_connected_goes_straight_out():
    client = _client()
    ws = _FakeWs()
    _connect(client, ws)

    client.send({"n": 1})

    assert len(ws.sent) == 1 and client.pending_count() == 0


def test_a_failed_send_stays_queued_and_keeps_order_after_reconnect():
    client = _client()
    broken = _FakeWs(fail_after=0)
    _connect(client, broken)
    client.send({"n": 1})
    client.send({"n": 2})
    assert client.pending_count() == 2

    client._on_closed()
    healthy = _FakeWs()
    _connect(client, healthy)

    assert [json.loads(m)["n"] for m in healthy.sent] == [1, 2]


def test_flush_stops_at_the_first_failure_and_keeps_the_rest():
    client = _client()
    for i in range(5):
        client.send({"n": i})

    flaky = _FakeWs(fail_after=2)
    _connect(client, flaky)

    assert len(flaky.sent) == 2
    assert client.pending_count() == 3


def test_messages_sent_while_flushing_backlog_do_not_jump_the_queue():
    client = _client()
    client.send({"n": 0})
    ws = _FakeWs(fail_after=0)
    _connect(client, ws)
    client._ws = _FakeWs()
    client.send({"n": 1})

    assert client.pending_count() == 2
    client._on_open()

    assert [json.loads(m)["n"] for m in client._ws.sent] == [0, 1]


def test_queue_is_bounded_and_drops_the_oldest(monkeypatch):
    monkeypatch.setattr(client_module, "_MAX_PENDING_MESSAGES", 3)
    client = _client()

    for i in range(5):
        client.send({"n": i})
    ws = _FakeWs()
    _connect(client, ws)

    assert [json.loads(m)["n"] for m in ws.sent] == [2, 3, 4]
