import time

from app.infrastructure.output.max_pending_from_universe import start_max_pending_from_universe


class _FakeClient:
    def __init__(self):
        self.max_pending = None

    def set_max_pending(self, n):
        self.max_pending = n


class _FakeMarketdataClient:
    def __init__(self, total, fail_first=0):
        self._total = total
        self._fail_first = fail_first
        self.calls = 0

    def fetch_symbols(self, markets):
        self.calls += 1
        if self.calls <= self._fail_first:
            raise ConnectionError("marketdata-service not up yet")
        return [f"SYM{i}" for i in range(self._total)]


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_sets_max_pending_on_every_client_to_the_tracked_symbol_count():
    clients = [_FakeClient(), _FakeClient()]
    mkd = _FakeMarketdataClient(total=13_267)

    start_max_pending_from_universe(clients, lambda: mkd)

    assert _wait_until(lambda: clients[0].max_pending == 13_267)
    assert clients[1].max_pending == 13_267
    assert mkd.calls == 1


def test_retries_until_marketdata_is_reachable(monkeypatch):
    import app.infrastructure.output.max_pending_from_universe as mod
    monkeypatch.setattr(mod, "_RETRY_SECONDS", 0.01)
    clients = [_FakeClient()]
    mkd = _FakeMarketdataClient(total=500, fail_first=2)

    start_max_pending_from_universe(clients, lambda: mkd)

    assert _wait_until(lambda: clients[0].max_pending == 500)
    assert mkd.calls == 3
