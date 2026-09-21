import json
import logging
from datetime import datetime, timezone

from app.config import settings
from app.infrastructure.output.outbound_event_ws_client import OutboundEventWebSocketClient
from app.scanner.timeframe import extraer_timeframe_minutos, minutos_to_label

logger = logging.getLogger(__name__)


def _ws_url(http_url: str, path: str) -> str:
    return http_url.replace("http://", "ws://").replace("https://", "wss://") + path


_log_service_client = OutboundEventWebSocketClient(
    _ws_url(settings.log_service_url, "/ws/internal/logs"), "log-service")
_notification_service_client = OutboundEventWebSocketClient(
    _ws_url(settings.notification_service_url, "/ws/internal/notificaciones/estado-escaner"), "notification-service")
_scanner_management_client = OutboundEventWebSocketClient(
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
