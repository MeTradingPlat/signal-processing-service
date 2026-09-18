import json
import logging
import threading
import time
from datetime import datetime, timezone

from app.config import settings
from app.scanner.timeframe import extraer_timeframe_minutos, minutos_to_label

logger = logging.getLogger(__name__)

_RECONNECT_BASE_DELAY = 3.0
_RECONNECT_MAX_DELAY = 30.0
_PING_INTERVAL_SECONDS = 25
_PING_TIMEOUT_SECONDS = 10


class _OutboundEventWebSocketClient:
    """Conexion WS saliente persistente con reconexion (mismo patron que
    RealtimeCandleClient) -- reemplaza un KafkaProducer.send() puntual. Un
    envio con la conexion caida se descarta (mismo best-effort que Kafka con
    retries=3 y despues loguear el error), pero a diferencia del productor de
    Kafka viejo, la reconexion la mantiene un hilo propio en vez de un objeto
    cacheado para siempre que nunca se reintenta solo."""

    def __init__(self, ws_url: str, etiqueta: str):
        self._ws_url = ws_url
        self._etiqueta = etiqueta
        self._ws = None
        self._reconnect_attempts = 0
        self._stop = False
        self._thread = threading.Thread(target=self._run_forever, daemon=True,
                                         name=f"ws-out-{etiqueta}")
        self._thread.start()

    def send(self, payload: dict) -> None:
        ws = self._ws
        if ws is None:
            logger.warning("%s: WS no disponible, se descarta el envio", self._etiqueta)
            return
        try:
            ws.send(json.dumps(payload, default=str))
        except Exception as e:
            logger.error("%s: fallo enviando por WS: %s", self._etiqueta, e)

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
                    # El Gateway exige este header en todas las rutas internas
                    # (GatewayHeaderFilter del lado Java) -- sin el, el
                    # handshake devuelve 403 antes de abrir el socket. Mismo
                    # requisito que ya usa RealtimeCandleClient.
                    header=["X-Gateway-Passed: true"],
                    on_open=lambda ws: self._on_open(),
                    on_error=lambda ws, err: logger.warning("%s: ws error: %s", self._etiqueta, err),
                )
                self._ws.run_forever(ping_interval=_PING_INTERVAL_SECONDS, ping_timeout=_PING_TIMEOUT_SECONDS)
            except Exception as e:
                logger.warning("%s: connection failed: %s", self._etiqueta, e)
            self._ws = None
            if self._stop:
                return
            delay = min(_RECONNECT_BASE_DELAY * (2 ** self._reconnect_attempts), _RECONNECT_MAX_DELAY)
            self._reconnect_attempts += 1
            time.sleep(delay)

    def _on_open(self) -> None:
        logger.info("%s: connected to %s", self._etiqueta, self._ws_url)
        self._reconnect_attempts = 0


def _ws_url(http_url: str, path: str) -> str:
    return http_url.replace("http://", "ws://").replace("https://", "wss://") + path


_log_service_client = _OutboundEventWebSocketClient(
    _ws_url(settings.log_service_url, "/ws/internal/logs"), "log-service")
_notification_service_client = _OutboundEventWebSocketClient(
    _ws_url(settings.notification_service_url, "/ws/internal/notificaciones/estado-escaner"), "notification-service")
_scanner_management_client = _OutboundEventWebSocketClient(
    _ws_url(settings.scanner_management_url, "/ws/internal/estado-escaner"), "scanner-management-service")


def publish_signals(scanner_id: int, scanner_name: str, signals: dict, nuevos: set):
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # El tab "Señales" del frontend lee de log-service (categoria=SIGNAL) --
    # es un log historico append-only. Publicar solo `nuevos` (no todo
    # `signals`) -- ver Escaner.permitirMultiplesSenales en symbols.py.
    signal_count = 0
    for symbol in nuevos:
        passed_matches = signals.get(symbol)
        if symbol not in signals:
            continue
        filtros_nombres = ", ".join([sm.filtro.enumFiltro.name for sm in passed_matches])
        detalle_filtros = f": cumple {filtros_nombres}" if filtros_nombres else ""
        precio_senal = passed_matches[-1].precio if passed_matches else None
        metadatos_json = json.dumps({
            "precio": precio_senal,
            "matches": [
                {
                    "filtro": sm.filtro.enumFiltro.name,
                    "timeframe": minutos_to_label(extraer_timeframe_minutos(sm.filtro)),
                    "velaTimestamp": sm.vela_timestamp.replace(tzinfo=None).isoformat(),
                }
                for sm in passed_matches
            ],
        })
        log_event = {
            "servicioOrigen": settings.servicio_origen,
            "nivel": "INFO",
            "mensaje": f"Señal generada para {symbol} en '{scanner_name}'{detalle_filtros}",
            "idEscaner": scanner_id,
            "symbol": symbol,
            "categoria": "SIGNAL",
            "timestamp": now,
            "metadatos": metadatos_json,
            "esSenalNueva": True,
        }
        try:
            _log_service_client.send(log_event)
        except Exception as e:
            logger.error("Failed to publish signal for %s: %s", symbol, e)
            continue
        signal_count += 1
        logger.debug("SIGNAL: scanner='%s' symbol=%s filters=%s", scanner_name, symbol, filtros_nombres)

    logger.info("SIGNALS: scanner='%s' count=%d", scanner_name, signal_count)


def publish_scanner_state(scanner_id: int, estado_nuevo: str, razon: str):
    event = {
        "idEscaner": scanner_id,
        "nombreEscaner": "",
        "estadoAnterior": "INICIADO",
        "estadoNuevo": estado_nuevo,
        "razon": razon,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "servicioOrigen": settings.servicio_origen,
    }
    _notification_service_client.send(event)
    _scanner_management_client.send(event)
    logger.info("SCANNER STATE: published id=%d estado=%s", scanner_id, estado_nuevo)
