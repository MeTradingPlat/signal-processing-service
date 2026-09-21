import httpx
import pytest

from app.adapters.log_service_client import LogServiceClient


def _client(handler):
    client = LogServiceClient(sleep=lambda _s: None)
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_returns_the_signaled_symbols():
    client = _client(lambda request: httpx.Response(200, json=["AAPL", "MSFT"]))

    assert client.get_signaled_today(1) == {"AAPL", "MSFT"}


def test_a_timeout_is_retried_and_the_next_attempt_wins():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json=["AAPL"])

    assert _client(handler).get_signaled_today(1) == {"AAPL"}
    assert len(calls) == 2


def test_gives_up_after_three_attempts():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(httpx.ReadTimeout):
        _client(handler).get_signaled_today(1)
    assert len(calls) == 3


def test_a_client_error_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(403)

    with pytest.raises(httpx.HTTPStatusError):
        _client(handler).get_signaled_today(1)
    assert len(calls) == 1


def test_a_server_error_is_retried():
    responses = iter([httpx.Response(503), httpx.Response(200, json=["AAPL"])])

    assert _client(lambda request: next(responses)).get_signaled_today(1) == {"AAPL"}
