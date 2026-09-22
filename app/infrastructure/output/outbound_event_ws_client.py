import json
import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

_RECONNECT_BASE_DELAY = 3.0
_RECONNECT_MAX_DELAY = 30.0
_PING_INTERVAL_SECONDS = 25
_PING_TIMEOUT_SECONDS = 10
_MAX_PENDING_MESSAGES = 10_000


class OutboundEventWebSocketClient:
    def __init__(self, ws_url: str, etiqueta: str, start: bool = True, max_pending: int = _MAX_PENDING_MESSAGES):
        self._ws_url = ws_url
        self._etiqueta = etiqueta
        self._ws = None
        self._open = False
        self._lock = threading.Lock()
        self._pending: deque[str] = deque()
        self._dropped = 0
        self._max_pending = max_pending
        self._reconnect_attempts = 0
        self._stop = False
        self._thread = threading.Thread(target=self._run_forever, daemon=True,
                                        name=f"ws-out-{etiqueta}")
        if start:
            self._thread.start()

    def set_max_pending(self, max_pending: int) -> None:
        with self._lock:
            self._max_pending = max_pending

    def send(self, payload: dict) -> None:
        message = json.dumps(payload, default=str)
        with self._lock:
            if self._open and not self._pending and self._try_send(message):
                return
            self._enqueue(message)

    def stop(self) -> None:
        self._stop = True
        if self._ws is not None:
            self._ws.close()

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def _try_send(self, message: str) -> bool:
        try:
            self._ws.send(message)
            return True
        except Exception as e:
            logger.error("%s: fallo enviando por WS, queda en cola: %s", self._etiqueta, e)
            return False

    def _enqueue(self, message: str) -> None:
        if len(self._pending) >= self._max_pending:
            self._pending.popleft()
            self._dropped += 1
            if self._dropped % 1000 == 1:
                logger.error("%s: cola de envio llena, descartando los mas viejos (%d descartados)",
                             self._etiqueta, self._dropped)
        self._pending.append(message)
        if len(self._pending) == 1:
            logger.warning("%s: WS no disponible, los envios quedan en cola hasta reconectar", self._etiqueta)

    def _flush_pending(self) -> int:
        flushed = 0
        while self._pending and self._try_send(self._pending[0]):
            self._pending.popleft()
            flushed += 1
        return flushed

    def _run_forever(self) -> None:
        while not self._stop:
            try:
                import websocket
                self._ws = websocket.WebSocketApp(
                    self._ws_url,
                    header=["X-Gateway-Passed: true"],
                    on_open=lambda ws: self._on_open(),
                    on_error=lambda ws, err: logger.warning("%s: ws error: %s", self._etiqueta, err),
                )
                self._ws.run_forever(ping_interval=_PING_INTERVAL_SECONDS, ping_timeout=_PING_TIMEOUT_SECONDS)
            except Exception as e:
                logger.warning("%s: connection failed: %s", self._etiqueta, e)
            self._on_closed()
            if self._stop:
                return
            delay = min(_RECONNECT_BASE_DELAY * (2 ** self._reconnect_attempts), _RECONNECT_MAX_DELAY)
            self._reconnect_attempts += 1
            time.sleep(delay)

    def _on_open(self) -> None:
        logger.info("%s: connected to %s", self._etiqueta, self._ws_url)
        self._reconnect_attempts = 0
        with self._lock:
            self._open = True
            flushed = self._flush_pending()
        if flushed:
            logger.info("%s: %d envios en cola entregados al conectar", self._etiqueta, flushed)

    def _on_closed(self) -> None:
        with self._lock:
            self._open = False
            self._ws = None
