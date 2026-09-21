from app.scanner.signal_baseline import SignalBaseline


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class _LogClient:
    def __init__(self, signaled=None, error=None):
        self._signaled = signaled
        self._error = error

    def get_signaled_today(self, scanner_id):
        if self._error:
            raise self._error
        return self._signaled


def test_consume_returns_true_once_for_a_signaled_symbol():
    baseline = SignalBaseline({"AAPL"})

    assert baseline.consume("AAPL") is True
    assert baseline.consume("AAPL") is False
    assert baseline.consume("MSFT") is False


def test_consume_all_returns_only_the_signaled_ones_among_the_given():
    baseline = SignalBaseline({"AAPL", "TSLA"})

    assert baseline.consume_all(["AAPL", "MSFT"]) == {"AAPL"}


def test_the_baseline_expires_after_its_ttl():
    clock = _Clock()
    baseline = SignalBaseline({"AAPL"}, ttl_seconds=600, clock=clock)
    clock.now = 601

    assert baseline.consume("AAPL") is False


def test_load_is_empty_when_multiple_signals_are_not_enabled():
    baseline = SignalBaseline.load(_LogClient({"AAPL"}), 1, enabled=False)

    assert baseline.consume("AAPL") is False


def test_load_reads_signaled_today_when_enabled():
    baseline = SignalBaseline.load(_LogClient({"AAPL"}), 1, enabled=True)

    assert baseline.consume("AAPL") is True


def test_load_falls_back_to_empty_when_log_service_fails():
    baseline = SignalBaseline.load(_LogClient(error=RuntimeError("down")), 1, enabled=True)

    assert baseline.consume("AAPL") is False
