import logging

from app.models.events import ScannerStoppedPayload
from app.orchestrator.process_registry import ProcessRegistry

logger = logging.getLogger(__name__)


def handle_scanner_stopped(registry: ProcessRegistry, payload: ScannerStoppedPayload):
    logger.info("Handler: SCANNER_STOPPED id=%d", payload.idEscaner)
    registry.remove(payload.idEscaner)
