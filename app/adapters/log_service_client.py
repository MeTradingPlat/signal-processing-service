import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LogServiceClient:
    def __init__(self):
        self._base = settings.log_service_url
        self._client = httpx.Client(headers={"X-Gateway-Passed": "true"})

    def get_signaled_today(self, scanner_id: int) -> set:
        resp = self._client.get(f"{self._base}/logs/escaner/{scanner_id}/signaled-today", timeout=5)
        resp.raise_for_status()
        return set(resp.json())
