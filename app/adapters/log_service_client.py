import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_ATTEMPTS = 3
_RETRY_PAUSE_SECONDS = 1.0
_TIMEOUT_SECONDS = 5


class LogServiceClient:
    def __init__(self, sleep=time.sleep):
        self._base = settings.log_service_url
        self._client = httpx.Client(headers={"X-Gateway-Passed": "true"})
        self._sleep = sleep

    def get_signaled_today(self, scanner_id: int) -> set:
        url = f"{self._base}/logs/escaner/{scanner_id}/signaled-today"
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                resp = self._client.get(url, timeout=_TIMEOUT_SECONDS)
                resp.raise_for_status()
                return set(resp.json())
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                if attempt == _ATTEMPTS or not _is_transient(e):
                    raise
                logger.warning("signaled-today intento %d/%d fallo (%s: %s), reintentando", attempt, _ATTEMPTS,
                               type(e).__name__, e)
                self._sleep(_RETRY_PAUSE_SECONDS)


def _is_transient(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    return True
