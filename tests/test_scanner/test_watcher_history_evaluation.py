import time

from tests.test_scanner.test_realtime_filter_watcher import _filtro_confirmation_candle, _make_watcher


def _history(last_bar_start: int) -> list[dict]:
    return [
        {"time": last_bar_start - 120, "open": 10, "high": 10, "low": 9, "close": 9.5, "closed": True},
        {"time": last_bar_start - 60, "open": 9.5, "high": 10.5, "low": 9.5, "close": 10, "closed": True},
        {"time": last_bar_start, "open": 11, "high": 15, "low": 11, "close": 15, "closed": True},
    ]


def _watcher_for_aapl():
    watcher, published = _make_watcher()
    watcher.configurar_grupos({1: [_filtro_confirmation_candle()]})
    watcher.actualizar_universo({"AAPL"})
    return watcher, published


def _last_closed_minute() -> int:
    return int(time.time()) // 60 * 60 - 60


def test_a_fresh_history_that_already_qualifies_publishes_without_waiting_for_the_next_bar():
    watcher, published = _watcher_for_aapl()

    watcher._client.on_history("AAPL", "M1", _history(_last_closed_minute()))

    assert [symbol for symbol, _ in published] == ["AAPL"]


def test_the_same_history_delivered_again_is_not_evaluated_twice():
    watcher, published = _watcher_for_aapl()
    history = _history(_last_closed_minute())

    watcher._client.on_history("AAPL", "M1", history)
    watcher._client.on_history("AAPL", "M1", history)

    assert len(published) == 1


def test_a_stale_history_is_seeded_but_not_evaluated():
    watcher, published = _watcher_for_aapl()

    watcher._client.on_history("AAPL", "M1", _history(_last_closed_minute() - 3 * 3600))

    assert published == []
    assert len(watcher._candles[("AAPL", "M1")]) == 3


def test_a_live_bar_after_the_history_evaluation_extends_the_buffer_and_is_marked_as_evaluated():
    watcher, _ = _watcher_for_aapl()
    minute = _last_closed_minute()
    watcher._client.on_history("AAPL", "M1", _history(minute))

    watcher._client.on_bar("AAPL", "M1", {
        "time": minute + 60, "open": 15, "high": 20, "low": 15, "close": 20, "closed": True,
    })

    assert len(watcher._candles[("AAPL", "M1")]) == 4
    assert watcher._last_evaluated[("AAPL", "M1")].timestamp() == minute + 60
