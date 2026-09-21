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


def _group_by_timeframe(keys: set[tuple[str, str]]) -> dict[str, list[str]]:
    """Funcion libre (no metodo) a proposito -- se puede probar sin
    instanciar RealtimeCandleClient, que arranca un hilo real conectando a
    un WS apenas se construye."""
    by_timeframe: dict[str, list[str]] = {}
    for symbol, timeframe in keys:
        by_timeframe.setdefault(timeframe, []).append(symbol)
    return by_timeframe


def _frames(action: str, keys: set[tuple[str, str]],
            bars_for: Callable[[str], int] | None) -> list[dict]:
    frames = []
    for timeframe, symbols in _group_by_timeframe(keys).items():
        frame = {"action": action, "symbols": symbols, "timeframe": timeframe}
        if action == "subscribe":
            frame["closedOnly"] = True
            if bars_for is not None:
                frame["bars"] = bars_for(timeframe)
        frames.append(frame)
    return frames


class RealtimeCandleClient:
    """Cliente WS hacia /ws/candles de marketdata-service -- el mismo
    endpoint que ya usa el frontend (candle-stream.service.ts) para
    graficar velas en vivo. Multiplexa varias suscripciones symbol:timeframe
    sobre un solo socket, con reconexion con backoff -- mismo patron que el
    cliente Angular, adaptado a un hilo de fondo sincrono en vez de RxJS."""

    def __init__(self, ws_url: str, on_history: Callable[[str, str, list[dict]], None],
                 on_bar: Callable[[str, str, dict], None],
                 bars_for: Callable[[str], int] | None = None):
        self._ws_url = ws_url
        self._bars_for = bars_for
        self._on_history = on_history
        self._on_bar = on_bar
        self._lock = threading.Lock()
        self._desired: set[tuple[str, str]] = set()
        self._subscribed: set[tuple[str, str]] = set()
        self._ws = None
        self._reconnect_attempts = 0
        self._stop = False
        self._thread = threading.Thread(target=self._run_forever, daemon=True, name="realtime-candle-client")
        self._thread.start()

    def update_subscriptions(self, keys: set[tuple[str, str]]) -> None:
        with self._lock:
            self._desired = set(keys)
        self._sync_subscriptions()

    def change_subscriptions(self, add: set[tuple[str, str]], remove: set[tuple[str, str]]) -> None:
        """Cambio puntual (un simbolo que sube o baja de grupo): a diferencia
        de update_subscriptions no recorre el conjunto completo, asi que su
        costo no crece con el tamaño del universo."""
        with self._lock:
            self._desired |= add
            self._desired -= remove
            if self._ws is None:
                return
            to_add = add - self._subscribed
            to_remove = remove & self._subscribed
            self._subscribed |= to_add
            self._subscribed -= to_remove
        self._send_batched("subscribe", to_add)
        self._send_batched("unsubscribe", to_remove)

    def stop(self) -> None:
        self._stop = True
        if self._ws is not None:
            self._ws.close()

    def _sync_subscriptions(self) -> None:
        if self._ws is None:
            return
        with self._lock:
            to_add = self._desired - self._subscribed
            to_remove = self._subscribed - self._desired
            self._subscribed = set(self._desired)
        self._send_batched("subscribe", to_add)
        self._send_batched("unsubscribe", to_remove)

    def _send_batched(self, action: str, keys: set[tuple[str, str]]) -> None:
        """Un mensaje por timeframe con TODOS los simbolos de ese timeframe,
        no uno por (simbolo, timeframe) -- con miles de simbolos elegibles
        de golpe (ej. al arrancar el dia), un mensaje por simbolo dejaba a
        marketdata-service pidiendo el historial uno a uno, en fila, sobre
        el mismo socket (confirmado que eso tardaba un buen rato en ponerse
        al dia). El servidor ya soporta `symbols` en vez de `symbol` para
        esto (ver candleSubscribeRequest en candle_ws_session.go)."""
        for frame in _frames(action, keys, self._bars_for):
            self._send(frame)

    def _send(self, frame: dict) -> None:
        try:
            if self._ws is not None:
                self._ws.send(json.dumps(frame))
        except Exception as e:
            logger.warning("RealtimeCandleClient: failed to send %s: %s", frame, e)

    def _run_forever(self) -> None:
        while not self._stop:
            try:
                import websocket
                self._ws = websocket.WebSocketApp(
                    self._ws_url,
                    # marketdata-service exige este header en TODAS sus rutas
                    # internas (X-Gateway-Passed), incluida /ws/candles -- sin
                    # el, el handshake devuelve 403 antes de llegar a abrir el
                    # socket. Confirmado en vivo el 2026-09-10.
                    header=["X-Gateway-Passed: true"],
                    on_open=lambda ws: self._on_open(),
                    on_message=lambda ws, msg: self._on_message(msg),
                    on_error=lambda ws, err: logger.warning("RealtimeCandleClient: ws error: %s", err),
                )
                self._ws.run_forever(ping_interval=_PING_INTERVAL_SECONDS, ping_timeout=_PING_TIMEOUT_SECONDS)
            except Exception as e:
                logger.warning("RealtimeCandleClient: connection failed: %s", e)
            if self._stop:
                return
            delay = min(_RECONNECT_BASE_DELAY * (2 ** self._reconnect_attempts), _RECONNECT_MAX_DELAY)
            self._reconnect_attempts += 1
            time.sleep(delay)

    def _on_open(self) -> None:
        logger.info("RealtimeCandleClient: connected to %s", self._ws_url)
        # Resetear solo en una conexion de verdad exitosa -- antes esto se
        # reseteaba en cada vuelta del loop ANTES de intentar conectar, asi
        # que el backoff exponencial nunca crecia (siempre calculaba con
        # _reconnect_attempts=0): reintentaba cada 3s indefinidamente contra
        # un servidor caido en vez de espaciarse hasta 30s.
        self._reconnect_attempts = 0
        with self._lock:
            self._subscribed = set()
        self._sync_subscriptions()

    def _on_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return
        msg_type = msg.get("type")
        if msg_type == "history":
            self._on_history(msg["symbol"], msg["timeframe"], msg.get("bars", []))
        elif msg_type == "bar" and msg.get("bar", {}).get("closed"):
            self._on_bar(msg["symbol"], msg["timeframe"], msg["bar"])
