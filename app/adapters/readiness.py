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
    scanner_ready = marketdata_reachable = fundamentals_ready = False

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        scanner_ready = scanner_ready or scanner_client.is_ready()
        marketdata_reachable = marketdata_reachable or marketdata_client.is_ready()
        # marketdata populates fundamentals lazily on first request rather than
        # preloading them, so being reachable doesn't mean it can serve real
        # data yet (e.g. its TastyTrade session may still be authenticating).
        # Confirm a sample comes back with actual values before starting
        # scanners, otherwise the first cycles would score static filters
        # against empty fundamentals and reject everything.
        if marketdata_reachable and not fundamentals_ready:
            fundamentals_ready = marketdata_client.fundamentals_ready()

        if scanner_ready and fundamentals_ready:
            logger.info("Readiness: scanner-management reachable and marketdata fundamentals ready")
            return

        logger.info(
            "Readiness: waiting for dependencies (scanner-management=%s, marketdata_reachable=%s, fundamentals_ready=%s), attempt %d/%d",
            scanner_ready, marketdata_reachable, fundamentals_ready, attempt, _MAX_ATTEMPTS,
        )
        time.sleep(_RETRY_SECONDS)

    logger.error(
        "Readiness: dependencies still unreachable after %d attempts, starting anyway",
        _MAX_ATTEMPTS,
    )
