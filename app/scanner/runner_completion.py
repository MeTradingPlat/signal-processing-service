import logging

logger = logging.getLogger(__name__)


def publish_scanner_completed(scanner_id: int):
    from app.adapters.scanner_management_client import ScannerManagementClient
    from app.infrastructure.output.event_ws_producer import publish_scanner_state

    ScannerManagementClient().notify_scanner_stopped(scanner_id)
    publish_scanner_state(scanner_id, "DETENIDO", "ESCANER_UNA_VEZ completado")
    logger.info("Scanner %d completed, notified scanner-management + WS", scanner_id)
