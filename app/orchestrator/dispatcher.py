import logging
from typing import Callable

from app.models.escaner import Escaner
from app.models.events import EventType, ScannerStoppedPayload, TunnelMessage
from app.orchestrator.handler_started import handle_scanner_started
from app.orchestrator.handler_stopped import handle_scanner_stopped
from app.orchestrator.process_registry import ProcessRegistry

logger = logging.getLogger(__name__)

Handler = Callable[[ProcessRegistry, Escaner | ScannerStoppedPayload], None]


class Dispatcher:

    def __init__(self, registry: ProcessRegistry):
        self._registry = registry
        self._routes: dict[str, Handler] = {
            EventType.SCANNER_STARTED: handle_scanner_started,
            EventType.SCANNER_STOPPED: handle_scanner_stopped,
        }

    def dispatch(self, message: TunnelMessage):
        handler = self._routes.get(message.type)
        if handler is None:
            logger.warning("Dispatcher: unknown event type '%s'", message.type)
            return
        payload = self._parse_payload(message)
        handler(self._registry, payload)

    def _parse_payload(self, message: TunnelMessage) -> Escaner | ScannerStoppedPayload:
        if message.type == EventType.SCANNER_STARTED:
            return Escaner.model_validate(message.payload)
        if message.type == EventType.SCANNER_STOPPED:
            return ScannerStoppedPayload.model_validate(message.payload)
        return message.payload
