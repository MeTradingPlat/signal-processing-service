import logging
from typing import List

import httpx

from app.config import settings
from app.models.escaner import Escaner

logger = logging.getLogger(__name__)


class ScannerManagementClient:
    def __init__(self):
        self._base = settings.scanner_management_url
        self._client = httpx.Client(headers={"Content-Type": "application/json", "X-Gateway-Passed": "true"})

    def _request(self, method: str, path: str, body: dict | None = None) -> dict | list:
        resp = self._client.request(method, f"{self._base}{path}", json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def is_ready(self) -> bool:
        try:
            self._request("GET", "/escaner/iniciados")
            return True
        except Exception:
            return False

    def get_active_scanners(self) -> List[Escaner]:
        try:
            raw = self._request("GET", "/escaner/iniciados")
            scanners = [Escaner(**s) for s in raw]
            logger.info("Sync: found %d active scanners", len(scanners))
            return scanners
        except Exception as e:
            logger.error("Sync: failed to get active scanners: %s", e)
            return []

    def notify_scanner_stopped(self, scanner_id: int):
        try:
            self._request("POST", f"/escaner/estado/{scanner_id}/detener")
            logger.info("Notified scanner-management: scanner %d stopped", scanner_id)
        except Exception as e:
            logger.error("Failed to notify scanner stop id=%d: %s", scanner_id, e)
