import logging
import time

from app.adapters.scanner_management_client import ScannerManagementClient
from app.scanner.marketdata_client import MarketdataClient

logger = logging.getLogger(__name__)

_RETRY_SECONDS = 5.0
_MAX_ATTEMPTS = 60


def wait_for_dependencies():
    scanner_client = ScannerManagementClient()
    marketdata_client = MarketdataClient()
    scanner_ready = marketdata_ready = False

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        scanner_ready = scanner_ready or scanner_client.is_ready()
        marketdata_ready = marketdata_ready or marketdata_client.is_ready()

        if scanner_ready and marketdata_ready:
            logger.info("Readiness: scanner-management and marketdata are reachable")
            return

        logger.info(
            "Readiness: waiting for dependencies (scanner-management=%s, marketdata=%s), attempt %d/%d",
            scanner_ready, marketdata_ready, attempt, _MAX_ATTEMPTS,
        )
        time.sleep(_RETRY_SECONDS)

    logger.error(
        "Readiness: dependencies still unreachable after %d attempts, starting anyway",
        _MAX_ATTEMPTS,
    )
