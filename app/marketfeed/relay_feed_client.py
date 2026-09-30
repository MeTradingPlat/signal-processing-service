import json
import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

_RECONNECT_BASE_DELAY = 3.0
_RECONNECT_MAX_DELAY = 30.0
_PING_INTERVAL_SECONDS = 25
_PING_TIMEOUT_SECONDS = 10


class RelayFeedClient:
    """Cliente WS generico para /ws/fundamentals y /ws/snapshot de
    marketdata-service -- los dos comparten el mismo protocolo minimo
    ({"action":"subscribe","symbol":...} por simbolo, sin lotes ni
    historial) y empujan {"type":..., "symbol":..., <data_key>:{...}} cada
    vez que ese dato cambia. Una sola instancia cubre el universo completo,
    reusada por fundamentals y snapshot con su propio ws_url/data_key (ver
    app/marketfeed/service.py) -- NO abre ninguna conexion a DxLink, es un
    fan-out interno de datos que marketdata-service ya tiene en su cache."""

    def __init__(self, ws_url: str, data_key: str, symbols: list[str],
                 on_update: Callable[[str, dict], None]):
        self._ws_url = ws_url
        self._data_key = data_key
        self._symbols = symbols
        self._on_update = on_update
        self._ws = None
        self._reconnect_attempts = 0
        self._stop = False
        self._thread = threading.Thread(target=self._run_forever, daemon=True, name=f"relay-feed-{data_key}")
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        if self._ws is not None:
            self._ws.close()

    def _run_forever(self) -> None:
        while not self._stop:
            try:
                import websocket
                self._ws = websocket.WebSocketApp(
                    self._ws_url,
                    header=["X-Gateway-Passed: true"],
                    on_open=lambda ws: self._on_open(),
                    on_message=lambda ws, msg: self._on_message(msg),
                    on_error=lambda ws, err: logger.warning("RelayFeedClient(%s): ws error: %s", self._data_key, err),
                )
                self._ws.run_forever(ping_interval=_PING_INTERVAL_SECONDS, ping_timeout=_PING_TIMEOUT_SECONDS)
            except Exception as e:
                logger.warning("RelayFeedClient(%s): connection failed: %s", self._data_key, e)
            if self._stop:
                return
            delay = min(_RECONNECT_BASE_DELAY * (2 ** self._reconnect_attempts), _RECONNECT_MAX_DELAY)
            self._reconnect_attempts += 1
            time.sleep(delay)

    def _on_open(self) -> None:
        logger.info("RelayFeedClient(%s): connected, subscribing %d symbols", self._data_key, len(self._symbols))
        self._reconnect_attempts = 0
        for symbol in self._symbols:
            self._send({"action": "subscribe", "symbol": symbol})

    def _send(self, frame: dict) -> None:
        try:
            if self._ws is not None:
                self._ws.send(json.dumps(frame))
        except Exception as e:
            logger.warning("RelayFeedClient(%s): failed to send %s: %s", self._data_key, frame, e)

    def _on_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return
        data = msg.get(self._data_key)
        symbol = msg.get("symbol")
        if symbol and data is not None:
            self._on_update(symbol, data)
