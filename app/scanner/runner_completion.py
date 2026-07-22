import logging

logger = logging.getLogger(__name__)


def publish_scanner_completed(scanner_id: int):
    from app.adapters.scanner_management_client import ScannerManagementClient
    from app.infrastructure.output.kafka_producer import publish_scanner_state

    ScannerManagementClient().notify_scanner_stopped(scanner_id)
    publish_scanner_state(scanner_id, "DETENIDO", "ESCANER_UNA_VEZ completado")
    _cleanup_scanner_data(scanner_id)
    logger.info("Scanner %d completed, notified scanner-management + Kafka + data cleanup", scanner_id)


def _cleanup_scanner_data(scanner_id: int):
    try:
        from app.adapters.scanner_management_client import ScannerManagementClient
        ScannerManagementClient().cleanup_scanner_data(scanner_id)
    except Exception as e:
        logger.warning("Failed to cleanup scanner %d data: %s", scanner_id, e)
